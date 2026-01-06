import frappe
from frappe.utils import getdate, today


@frappe.whitelist()
def get_gratuity(employee):
    emp = frappe.get_doc("Employee", employee)

    if not emp.date_of_joining or not emp.custom_basic_salary:
        return 0

    doj = getdate(emp.date_of_joining)
    current_date = getdate(today())

    total_months = (current_date.year - doj.year) * 12 + (current_date.month - doj.month)
    if total_months < 0:
        total_months = 0

    monthly_gratuity = ctc * 0.8

    total_gratuity = total_months * monthly_gratuity

    return total_gratuity
