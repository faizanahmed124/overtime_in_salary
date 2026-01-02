import frappe
from frappe.utils import date_diff, flt ,money_in_words


def calculate_overtime(doc, method ,):


   doc.custom_overtime_hours = 0
   doc.custom_overtime_amount = 0


   if not doc.employee or not doc.start_date or not doc.end_date:
       return


   employee = frappe.get_doc("Employee", doc.employee)


   if not employee.custom_allow_overtime:
       return


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


   if employee.employment_type == "Permanent":
       adjusted_salary = base_salary * 0.85
       month_days = date_diff(doc.end_date, doc.start_date) + 1
       per_day_salary = adjusted_salary / month_days
       per_hour_rate = per_day_salary / 8
       overtime_hour_rate = per_hour_rate * 1.5


       doc.custom_overtime_amount = flt(
           overtime_hour_rate * total_overtime, 2
       )


   elif employee.employment_type == "Daily Wages":
       per_hour_rate = base_salary / 8
       overtime_hour_rate = per_hour_rate * 1.5


       doc.custom_overtime_amount = flt(
           overtime_hour_rate * total_overtime, 2
       )


   # ✅ ADD OVERTIME INTO GROSS PAY
   doc.gross_pay = flt(doc.gross_pay) + flt(doc.custom_overtime_amount)


   # ================================
   # 7️⃣ NET PAY CALCULATION ONLY
   # ================================
   doc.net_pay = flt(doc.gross_pay) - flt(doc.total_deduction)
   doc.rounded_total = flt(doc.net_pay)
   doc.total_in_words = money_in_words(doc.rounded_total)

