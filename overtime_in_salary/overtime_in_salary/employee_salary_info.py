import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate


@frappe.whitelist()
def get_employee_salary_info(employee):
	"""Live salary structure / component / loan data for the Employee Salary tab.
	Nothing is cached or stored: every value is read from the submitted source documents."""
	frappe.has_permission("Employee", "read", employee, throw=True)

	return {
		"structure": get_salary_structure(employee),
		"loans": get_loan_history(employee),
		"advances": get_advance_history(employee),
	}


def get_salary_structure(employee):
	assignment = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", nowdate()]},
		["name", "salary_structure", "from_date", "base", "variable", "company"],
		order_by="from_date desc, creation desc",
		as_dict=True,
	)
	if not assignment:
		return None

	ss = frappe.get_doc("Salary Structure", assignment.salary_structure)
	shared_with = frappe.db.sql(
		"""SELECT COUNT(DISTINCT employee) FROM `tabSalary Structure Assignment`
		WHERE salary_structure = %s AND docstatus = 1""",
		ss.name,
	)[0][0]
	components = []
	for parentfield, kind in (("earnings", "Earning"), ("deductions", "Deduction")):
		for row in ss.get(parentfield):
			components.append(
				{
					"type": kind,
					"row_name": row.name,
					"component": row.salary_component,
					"abbr": row.abbr,
					"amount": flt(row.amount),
					"formula": row.formula if row.amount_based_on_formula else None,
					"amount_based_on_formula": cint(row.amount_based_on_formula),
					"condition": row.condition,
					"depends_on_payment_days": row.depends_on_payment_days,
					"do_not_include_in_total": row.do_not_include_in_total,
				}
			)

	return {
		"assignment": assignment.name,
		"salary_structure": assignment.salary_structure,
		"from_date": assignment.from_date,
		"base": flt(assignment.base),
		"variable": flt(assignment.variable),
		"payroll_frequency": ss.payroll_frequency,
		"is_active": ss.is_active,
		"modified": str(ss.modified),
		"shared_with": shared_with,
		"components": components,
		"component_options": {
			"Earning": frappe.get_all("Salary Component", {"type": "Earning", "disabled": 0}, pluck="name", order_by="name"),
			"Deduction": frappe.get_all("Salary Component", {"type": "Deduction", "disabled": 0}, pluck="name", order_by="name"),
		},
	}


@frappe.whitelist()
def save_salary_structure_components(employee, salary_structure, modified, components):
	"""Saves the edited component rows for this employee only.

	Runs through the normal Salary Structure validation, then dry-runs a salary slip for the
	employee. Any failure rolls the whole change back, so a bad formula can never reach payroll.
	If other employees share the structure, the edit goes to a copy assigned to this employee only."""
	frappe.has_permission("Employee", "read", employee, throw=True)
	frappe.has_permission("Salary Structure", "write", salary_structure, throw=True)
	components = json.loads(components) if isinstance(components, str) else components

	ss = frappe.get_doc("Salary Structure", salary_structure)
	if ss.docstatus == 2:
		frappe.throw(_("Salary Structure {0} is cancelled.").format(salary_structure))
	if str(ss.modified) != str(modified):
		frappe.throw(
			_("Salary Structure {0} was changed by someone else. Please reload and try again.").format(salary_structure),
			frappe.TimestampMismatchError,
		)

	current = {r.name: r for f in ("earnings", "deductions") for r in ss.get(f)}
	kept = set()
	new_rows = {"earnings": [], "deductions": []}
	for c in components:
		field = "earnings" if c.get("type") == "Earning" else "deductions"
		row = current.get(c.get("row_name")) if c.get("row_name") else None
		if row:
			kept.add(row.name)
		else:
			comp = c.get("component")
			if not comp or frappe.db.get_value("Salary Component", comp, "type") != c.get("type"):
				frappe.throw(_("Select a valid {0} component for every new row.").format(_(c.get("type") or "")))
			row = frappe.new_doc("Salary Detail", parent_doc=ss, parentfield=field)
			row.salary_component = comp
		row.amount_based_on_formula = cint(c.get("amount_based_on_formula"))
		row.formula = (c.get("formula") or "").strip() if row.amount_based_on_formula else None
		row.amount = 0 if row.amount_based_on_formula else flt(c.get("amount"))
		row.condition = (c.get("condition") or "").strip() or None
		row.do_not_include_in_total = cint(c.get("do_not_include_in_total"))
		new_rows[field].append(row)

	if not any(new_rows["earnings"]):
		frappe.throw(_("A Salary Structure needs at least one earning component."))

	for field, rows in new_rows.items():
		ss.set(field, [])
		for row in rows:
			ss.append(field, row)

	frappe.db.savepoint("employee_ss_edit")
	try:
		shared = _structure_employee_count(ss.name) > 1
		if shared:
			# never touch a structure other employees use: give this employee their own copy
			target = frappe.copy_doc(ss)
			target.name = target.__newname = _unique_structure_name(ss.name, employee)
			target.docstatus = 0
			target.insert()
			target.submit()
			_assign_structure(employee, target.name, nowdate(), get_salary_structure(employee))
		else:
			target = ss
			target.flags.ignore_validate_update_after_submit = True
			target.save()
		_dry_run_slip(target.name, employee)
	except Exception:
		frappe.db.rollback(save_point="employee_ss_edit")
		raise

	_recalc_employee_drafts(employee)
	return get_salary_structure(employee)


def _structure_employee_count(salary_structure):
	return frappe.db.sql(
		"""SELECT COUNT(DISTINCT employee) FROM `tabSalary Structure Assignment`
		WHERE salary_structure = %s AND docstatus = 1""",
		salary_structure,
	)[0][0]


def _unique_structure_name(base, employee):
	name = f"{base} - {employee}"
	i = 2
	while frappe.db.exists("Salary Structure", name):
		name = f"{base} - {employee} ({i})"
		i += 1
	return name


def check_no_draft_slips_on_old_structure(employee, new_structure):
	"""Blocks a structure change while the employee still has draft slips on a different structure.
	The drafts are left untouched; the user submits them first and then retries the change."""
	drafts = frappe.get_all(
		"Salary Slip",
		{"employee": employee, "docstatus": 0, "salary_structure": ["not in", ["", new_structure]]},
		["name", "salary_structure", "start_date", "end_date"],
		order_by="start_date",
	)
	if not drafts:
		return

	links = ", ".join(
		f"{frappe.utils.get_link_to_form('Salary Slip', d.name)} ({d.salary_structure}, {d.start_date} to {d.end_date})"
		for d in drafts
	)
	frappe.throw(
		_("Cannot change the Salary Structure of {0} while draft Salary Slips exist with the previous Salary Structure. "
		  "Please submit them first: {1}").format(employee, links),
		title=_("Draft Salary Slips Pending"),
	)


def validate_assignment_change(doc, method=None):
	"""Salary Structure Assignment validate hook: covers assignments created from the standard form."""
	if doc.is_new():
		check_no_draft_slips_on_old_structure(doc.employee, doc.salary_structure)


def _assign_structure(employee, salary_structure, from_date, current):
	"""Submits an assignment for the employee. An existing assignment on the same date is replaced."""
	check_no_draft_slips_on_old_structure(employee, salary_structure)
	for dup in frappe.get_all(
		"Salary Structure Assignment",
		{"employee": employee, "from_date": from_date, "docstatus": ["!=", 2]},
		["name", "docstatus"],
	):
		doc = frappe.get_doc("Salary Structure Assignment", dup.name)
		if dup.docstatus == 1:
			doc.cancel()
		else:
			doc.delete()

	ssa = frappe.new_doc("Salary Structure Assignment")
	ssa.employee = employee
	ssa.salary_structure = salary_structure
	ssa.from_date = from_date
	ssa.company = frappe.db.get_value("Employee", employee, "company")
	ssa.base = flt(current["base"]) if current else 0
	ssa.variable = flt(current["variable"]) if current else 0
	ssa.insert()
	ssa.submit()


def _dry_run_slip(salary_structure, employee):
	"""Calculates (never saves) a slip for the period the employee's current assignment covers."""
	from frappe.utils import get_first_day, get_last_day

	assignment = get_salary_structure(employee)
	today = getdate(nowdate())
	slip = frappe.new_doc("Salary Slip")
	slip.employee = employee
	slip.company = frappe.db.get_value("Employee", employee, "company")
	slip.posting_date = today
	slip.salary_structure = salary_structure
	slip.start_date = max(get_first_day(today), getdate(assignment["from_date"])) if assignment else get_first_day(today)
	slip.end_date = get_last_day(today)
	slip.payroll_frequency = frappe.db.get_value("Salary Structure", salary_structure, "payroll_frequency")
	try:
		slip.run_method("process_salary_structure", for_preview=1)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.throw(_("The change was not saved because a salary slip cannot be calculated with it: {0}").format(str(e)))


def _recalculate_drafts(salary_structure):
	from overtime_in_salary.overtime_in_salary.utils.salary_triggers import auto_recalculate_draft_slips

	employees = frappe.get_all(
		"Salary Structure Assignment",
		{"salary_structure": salary_structure, "docstatus": 1},
		pluck="employee",
		distinct=True,
	)
	for emp in employees:
		frappe.enqueue(auto_recalculate_draft_slips, queue="short", enqueue_after_commit=True, employee=emp)


@frappe.whitelist()
def change_salary_structure(employee, salary_structure, from_date):
	"""Assigns another Salary Structure to the employee from `from_date` (new submitted assignment,
	same base as the current one, so slips of earlier periods keep using the old structure)."""
	frappe.has_permission("Salary Structure Assignment", "create", throw=True)
	current = get_salary_structure(employee)
	frappe.db.savepoint("employee_ss_change")
	try:
		_assign_structure(employee, salary_structure, from_date, current)
		sync_employee_eobi(employee, salary_structure)
	except Exception:
		frappe.db.rollback(save_point="employee_ss_change")
		raise

	_recalc_employee_drafts(employee)
	return get_salary_structure(employee)


def sync_employee_eobi(employee, salary_structure):
	"""The structure decides EOBI: with an EOBI deduction the employee is EOBI applicable,
	without one the flag is cleared and the amount reset."""
	rows = [
		r for r in frappe.get_all(
			"Salary Detail",
			{"parent": salary_structure, "parentfield": "deductions"},
			["salary_component", "amount"],
		)
		if "EOBI" in (r.salary_component or "").upper()
	]
	if rows:
		amount = flt(frappe.db.get_value("Employee", employee, "custom_eobi_amount")) or flt(rows[0].amount)
		frappe.db.set_value("Employee", employee, {"custom_eobi_applicable": 1, "custom_eobi_amount": amount})
	else:
		frappe.db.set_value("Employee", employee, {"custom_eobi_applicable": 0, "custom_eobi_amount": 0})


def _recalc_employee_drafts(employee):
	from overtime_in_salary.overtime_in_salary.utils.salary_triggers import auto_recalculate_draft_slips

	frappe.enqueue(auto_recalculate_draft_slips, queue="short", enqueue_after_commit=True, employee=employee)


def _existing_fields(doctype, fields):
	meta = frappe.get_meta(doctype)
	return [f for f in fields if f in ("name", "docstatus", "creation") or meta.has_field(f)]


def get_loan_history(employee):
	"""Loans come from the Lending app. When it is not installed there is no loan data to show."""
	if not frappe.db.exists("DocType", "Loan"):
		return {"available": False, "loans": []}

	loan_fields = _existing_fields(
		"Loan",
		[
			"name", "loan_type", "status", "posting_date", "disbursement_date", "repayment_start_date",
			"loan_amount", "disbursed_amount", "total_payment", "total_principal_paid",
			"total_interest_payable", "total_amount_paid", "written_off_amount",
			"rate_of_interest", "repayment_periods", "monthly_repayment_amount",
		],
	)
	loans = frappe.get_all(
		"Loan",
		filters={"applicant_type": "Employee", "applicant": employee, "docstatus": 1},
		fields=loan_fields,
		order_by="posting_date asc, creation asc",
	)

	has_repayment = frappe.db.exists("DocType", "Loan Repayment")
	rep_meta = frappe.get_meta("Loan Repayment") if has_repayment else None
	for loan in loans:
		total_payment = flt(loan.get("total_payment")) or flt(loan.get("loan_amount"))
		paid = flt(loan.get("total_amount_paid"))
		loan["total_payable"] = total_payment
		loan["total_paid"] = paid
		loan["remaining"] = max(total_payment - paid - flt(loan.get("written_off_amount")), 0)
		loan["repayments"] = []
		if has_repayment:
			rep_fields = _existing_fields(
				"Loan Repayment",
				["name", "posting_date", "repayment_type", "amount_paid", "principal_amount_paid",
				 "total_interest_paid", "payable_amount", "payment_account"],
			)
			loan["repayments"] = frappe.get_all(
				"Loan Repayment",
				filters={"against_loan": loan.name, "docstatus": 1},
				fields=rep_fields,
				order_by="posting_date asc, creation asc",
			)
		loan["salary_slip_deductions"] = frappe.db.sql(
			"""
			SELECT ss.name AS salary_slip, ss.start_date, ss.end_date,
				ssl.total_payment, ssl.principal_amount, ssl.interest_amount
			FROM `tabSalary Slip Loan` ssl
			JOIN `tabSalary Slip` ss ON ss.name = ssl.parent
			WHERE ssl.loan = %s AND ss.docstatus = 1
			ORDER BY ss.start_date
			""",
			loan.name,
			as_dict=True,
		) if frappe.get_meta("Salary Slip Loan").has_field("loan") else []

	return {"available": True, "loans": loans}


def get_advance_history(employee):
	"""Employee Advances (HRMS) with paid / claimed / returned / pending balance."""
	fields = _existing_fields(
		"Employee Advance",
		["name", "posting_date", "purpose", "advance_amount", "paid_amount", "claimed_amount",
		 "return_amount", "pending_amount", "status"],
	)
	advances = frappe.get_all(
		"Employee Advance",
		filters={"employee": employee, "docstatus": 1},
		fields=fields,
		order_by="posting_date asc, creation asc",
	)
	for adv in advances:
		adv["pending"] = flt(adv.get("paid_amount")) - flt(adv.get("claimed_amount")) - flt(adv.get("return_amount"))
	return advances
