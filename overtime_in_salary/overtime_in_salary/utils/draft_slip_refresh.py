import frappe
from frappe.utils import flt


# ============================================================
# Full refresh of ONE draft Salary Slip when it is opened (form loader)
# ============================================================
def _fetch_fields(doc):
	"""Every plain field on the slip that is pulled from a linked document (fetch_from)."""
	return [
		df for df in doc.meta.fields
		if df.fetch_from and "." in df.fetch_from and not df.fetch_if_empty
		and df.fieldtype not in ("Table", "Table MultiSelect")
	]


def _refetch_linked_fields(doc):
	"""Re-pull all fetch_from fields (designation, department, branch, employee_name, ...)
	from their source document. Frappe only does this in the browser, never on the server."""
	for df in _fetch_fields(doc):
		link_field, source_field = df.fetch_from.split(".", 1)
		link_value = doc.get(link_field)
		if not link_value:
			continue
		link_df = doc.meta.get_field(link_field)
		if not link_df or link_df.fieldtype != "Link" or not link_df.options:
			continue
		value = frappe.db.get_value(link_df.options, link_value, source_field)
		if doc.get(df.fieldname) != value:
			doc.set(df.fieldname, value)


def _slip_snapshot(doc):
	"""Comparable picture of everything a refresh can change."""
	def rows(table):
		return sorted(
			(r.salary_component, flt(r.amount), flt(r.default_amount), bool(r.get("do_not_include_in_total")))
			for r in doc.get(table)
		)

	fields = [
		"start_date", "end_date", "gross_pay", "total_deduction", "net_pay", "rounded_total",
		"payment_days", "total_working_days", "leave_without_pay", "mode_of_payment",
		"bank_name", "bank_account_no", "salary_structure", "custom_overtime_hours",
		"custom_overtime_amount", "custom_less_duty_hour", "custom_less_duty_hours_amount",
		"custom_paid_salary", "custom_leave_with_pay", "custom_duty_hours",
	]
	fields += [df.fieldname for df in _fetch_fields(doc)]
	fields = [f for f in dict.fromkeys(fields) if doc.meta.has_field(f) and frappe.db.has_column("Salary Slip", f)]
	return ([doc.get(f) or 0 for f in fields], rows("earnings"), rows("deductions"))


@frappe.whitelist()
def refresh_draft_slip(name):
	"""Re-tally a DRAFT Salary Slip from every source (salary structure, attendance, leaves,
	additional salaries, employee master) so removed/changed items are reflected.
	Saves only when something actually changed. Returns {"updated": bool, "modified": str}."""
	doc = frappe.get_doc("Salary Slip", name)
	if doc.docstatus != 0:
		return {"updated": False}
	doc.check_permission("write")

	def result(updated):
		# "modified" lets the browser detect that its cached copy is stale even when this
		# call changed nothing (e.g. a background job already updated the slip).
		modified = frappe.db.get_value("Salary Slip", name, "modified")
		return {"updated": updated, "modified": str(modified)}

	before = _slip_snapshot(doc)
	try:
		_refetch_linked_fields(doc)
		doc.pull_emp_details()
		# rebuild earnings/deductions from the current salary structure + additional salaries
		doc.get_emp_and_working_day_details()
		# save() runs validate -> standard payroll maths + calculate_overtime hook
		doc.save()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Draft Salary Slip Refresh Failed", message=frappe.get_traceback())
		raise

	frappe.local.message_log = []   # silence the overtime popups; the loader is the only UI here

	if _slip_snapshot(doc) == before:
		frappe.db.rollback()   # nothing changed: keep modified timestamp / version log untouched
		return result(False)

	frappe.db.commit()
	return result(True)
