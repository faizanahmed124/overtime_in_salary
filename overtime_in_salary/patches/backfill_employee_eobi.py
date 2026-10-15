import frappe
from frappe.utils import flt, nowdate


def execute():
	"""EOBI Applicable / EOBI Amount were added to Employee after salary structures already carried
	an EOBI deduction. Copy the amount currently in force on each employee's structure so the
	checkbox reflects reality and slips keep deducting the same EOBI."""
	for emp in frappe.get_all("Employee", filters={"custom_eobi_applicable": 0}, pluck="name"):
		structure = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": emp, "docstatus": 1, "from_date": ["<=", nowdate()]},
			"salary_structure",
			order_by="from_date desc, creation desc",
		)
		if not structure:
			continue

		amount = frappe.db.sql(
			"""SELECT MAX(amount) FROM `tabSalary Detail`
			WHERE parent=%s AND parenttype='Salary Structure' AND parentfield='deductions'
			AND UPPER(salary_component) LIKE '%%EOBI%%' AND COALESCE(do_not_include_in_total, 0)=0""",
			structure,
		)[0][0]

		if flt(amount) > 0:
			frappe.db.set_value(
				"Employee", emp,
				{"custom_eobi_applicable": 1, "custom_eobi_amount": flt(amount)},
				update_modified=False,
			)
