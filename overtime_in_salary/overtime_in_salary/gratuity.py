import frappe
from frappe.utils import getdate, today, flt


def calculate_gratuity(date_of_joining, basic_salary):
    if not date_of_joining or not flt(basic_salary):
        return 0

    doj = getdate(date_of_joining)
    current_date = getdate(today())

    total_months = (current_date.year - doj.year) * 12 + (current_date.month - doj.month)
    if total_months < 0:
        total_months = 0

    return total_months * flt(basic_salary) * 0.8


def set_gratuity(doc, method=None):
    """Employee validate: save ke waqt hi field set ho jaye, extra save nahi."""
    doc.custom_gratuity = calculate_gratuity(doc.date_of_joining, doc.custom_basic_salary)


def update_all_gratuity():
    """Rozana scheduler: sab active employees ki gratuity update karo."""
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "date_of_joining", "custom_basic_salary", "custom_gratuity"],
    )
    for emp in employees:
        amount = calculate_gratuity(emp.date_of_joining, emp.custom_basic_salary)
        if flt(amount) != flt(emp.custom_gratuity):
            frappe.db.set_value(
                "Employee", emp.name, "custom_gratuity", amount, update_modified=False
            )
    frappe.db.commit()


@frappe.whitelist()
def get_gratuity(employee):
    emp = frappe.get_doc("Employee", employee)
    return calculate_gratuity(emp.date_of_joining, emp.custom_basic_salary)