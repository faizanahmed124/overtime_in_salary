import frappe

from overtime_in_salary.overtime_in_salary.salary_slip import calculate_overtime


# ============================================================
# 1. Bulk button-triggered recalculation (list view button)
# ============================================================
@frappe.whitelist()
def bulk_recalculate_selected_slips(names):
	"""List view se selected Salary Slips ko recalculate karta hai"""
	import json

	if isinstance(names, str):
		names = json.loads(names)

	done, failed, errors = 0, 0, []

	for name in names:
		try:
			doc = frappe.get_doc("Salary Slip", name)

			if doc.docstatus == 1:
				doc.flags.ignore_validate_update_after_submit = True

			# Employee master se mode_of_payment, bank_name, bank_account_no
			# dobara fetch karo — isi ki wajah se pehle update nahi ho raha tha.
			doc.pull_emp_details()

			doc.get_working_days_details(lwp=doc.leave_without_pay)
			doc.calculate_net_pay()
			calculate_overtime(doc, None)
			doc.save(ignore_permissions=True)
			frappe.db.commit()

			frappe.publish_realtime(
				event="salary_slip_auto_updated",
				message={"salary_slip": name, "employee": doc.employee},
				after_commit=True,
			)
			done += 1
		except Exception:
			frappe.db.rollback()
			failed += 1
			tb = frappe.get_traceback()
			errors.append(f"{name}: {tb}")
			frappe.log_error(title="Bulk Salary Slip Recalculation Failed", message=tb)

	return {"done": done, "failed": failed, "errors": errors}


# ============================================================
# 2. Auto-recalculate DRAFT slips for one employee (used by hooks)
# ============================================================
def auto_recalculate_draft_slips(employee, from_date=None, to_date=None):
	"""Employee ki DRAFT Salary Slips ko live recalculate karo"""
	filters = {
		"employee": employee,
		"docstatus": 0,   # sirf draft
	}

	if from_date and to_date:
		filters["start_date"] = ["<=", to_date]
		filters["end_date"] = [">=", from_date]

	slip_names = frappe.get_all("Salary Slip", filters=filters, pluck="name")

	for name in slip_names:
		try:
			doc = frappe.get_doc("Salary Slip", name)

			# Employee master se mode_of_payment, bank_name, bank_account_no
			# dobara fetch karo.
			doc.pull_emp_details()

			doc.get_working_days_details(lwp=doc.leave_without_pay)
			doc.calculate_net_pay()
			calculate_overtime(doc, None)
			doc.save(ignore_permissions=True)
			frappe.db.commit()

			frappe.publish_realtime(
				event="salary_slip_auto_updated",
				message={"salary_slip": name, "employee": employee},
				after_commit=True,
			)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="Draft Salary Slip Auto Recalc Failed", message=frappe.get_traceback())


# ============================================================
# 3. Doc event hooks (Attendance / Additional Salary / Employee)
# ============================================================
def on_attendance_change(doc, method):
	frappe.enqueue(
		auto_recalculate_draft_slips,
		queue="short",
		employee=doc.employee,
		from_date=doc.attendance_date,
		to_date=doc.attendance_date,
	)


def on_additional_salary_change(doc, method):
	frappe.enqueue(
		auto_recalculate_draft_slips,
		queue="short",
		employee=doc.employee,
		from_date=doc.payroll_date,
		to_date=doc.payroll_date,
	)


def on_employee_change(doc, method):
	changed = doc.get_doc_before_save()
	if not changed:
		return

	relevant_fields = [
		"custom_allow_overtime",
		"custom_income_tax_amount",
		"ctc",
		"employment_type",
		"salary_mode",       # Mode of Payment (bank/cash/cheque)
		"bank_name",
		"bank_ac_no",
	]
	if any(doc.get(f) != changed.get(f) for f in relevant_fields):
		frappe.enqueue(
			auto_recalculate_draft_slips,
			queue="short",
			employee=doc.name,
		)