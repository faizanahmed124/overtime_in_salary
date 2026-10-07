import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


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
	components = []
	for parentfield, kind in (("earnings", "Earning"), ("deductions", "Deduction")):
		for row in ss.get(parentfield):
			components.append(
				{
					"type": kind,
					"component": row.salary_component,
					"abbr": row.abbr,
					"amount": flt(row.amount),
					"formula": row.formula if row.amount_based_on_formula else None,
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
		"components": components,
	}


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
