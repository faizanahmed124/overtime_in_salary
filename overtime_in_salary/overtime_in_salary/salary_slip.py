import frappe
from frappe.utils import date_diff, flt

def calculate_overtime(doc, method):

    doc.custom_overtime_hours = 0
    doc.custom_overtime_amount = 0

    if not doc.employee or not doc.start_date or not doc.end_date:
        return

    # 1️⃣ Get employee
    employee = frappe.get_doc("Employee", doc.employee)

    # ✅ ONLY employees with Allow Overtime checked
    if not employee.custom_allow_overtime:
        return

    # 2️⃣ Total overtime hours from Attendance
    total_overtime = frappe.db.sql("""
        SELECT COALESCE(SUM(custom_overtime), 0)
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0][0]

    total_overtime = flt(total_overtime)
    doc.custom_overtime_hours = total_overtime

    if total_overtime == 0:
        return

    # 3️⃣ Get BASE salary from Salary Structure Assignment
    base_salary = frappe.db.get_value(
        "Salary Structure Assignment",
        {
            "employee": doc.employee,
            "docstatus": 1,
            "from_date": ["<=", doc.start_date]
        },
        "base"
    )

    base_salary = flt(base_salary)
    if base_salary == 0:
        return

    # ================================
    # 4️⃣ PERMANENT EMPLOYEE LOGIC
    # ================================
    if employee.employment_type == "Permanent":

        adjusted_salary = base_salary * 0.85
        month_days = date_diff(doc.end_date, doc.start_date) + 1
        per_day_salary = adjusted_salary / month_days
        per_hour_rate = per_day_salary / 8
        overtime_hour_rate = per_hour_rate * 1.5

        doc.custom_overtime_amount = flt(
            overtime_hour_rate * total_overtime, 2
        )

    # ================================
    # 5️⃣ DAILY WAGES EMPLOYEE LOGIC
    # ================================
    elif employee.employment_type == "Daily Wages":

        # base = per day salary
        per_hour_rate = base_salary / 8
        overtime_hour_rate = per_hour_rate * 1.5

        doc.custom_overtime_amount = flt(
            overtime_hour_rate * total_overtime, 2
        )
