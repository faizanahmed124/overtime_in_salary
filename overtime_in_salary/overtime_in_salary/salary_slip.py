import frappe
from frappe.utils import date_diff, flt, money_in_words
from decimal import Decimal, ROUND_HALF_UP

def round_to_two_decimals(value):
    """Round to 2 decimal places - .5 rounds up, otherwise nearest"""
    d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(d)

def round_to_integer(value):
    """Round to nearest integer - .5 rounds up"""
    d = Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(d)

def calculate_overtime(doc, method):
    # Initialize fields
    doc.custom_overtime_hours = 0
    doc.custom_overtime_amount = 0
    doc.custom_per_day_rate = 0
    doc.custom_overtime_rate = 0
    doc.custom_duty_hours = 0

    if not doc.employee or not doc.start_date or not doc.end_date:
        frappe.msgprint(
            title="⚠️ Overtime Calculation Skipped",
            msg="Missing employee, start date, or end date",
            indicator="orange"
        )
        return

    employee = frappe.get_doc("Employee", doc.employee)

    if not employee.custom_allow_overtime:
        frappe.msgprint(
            title="⚠️ Overtime Not Allowed",
            msg=f"Employee {doc.employee} does not have overtime allowed",
            indicator="orange"
        )
        return

    # ================================
    # 1 GET BASE SALARY
    # ================================
    base_salary = frappe.db.get_value(
        "Salary Structure Assignment",
        {
            "employee": doc.employee,
            "docstatus": 1,
            "from_date": ["<=", doc.start_date]
        },
        "base",
        order_by="from_date DESC"
    )

    base_salary = flt(base_salary)
    doc.custom_per_day_rate = flt(base_salary, 2)

    if base_salary == 0:
        frappe.msgprint(
            title="⚠️ No Base Salary Found",
            msg=f"No active salary structure found for employee {doc.employee}",
            indicator="red"
        )
        return

    # ================================
    # 2 TOTAL OVERTIME HOURS
    # ================================
    total_overtime = frappe.db.sql("""
        SELECT COALESCE(SUM(custom_overtime),0)
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0

    doc.custom_overtime_hours = total_overtime

    # ================================
    # 3 TOTAL DUTY HOURS
    # ================================
    total_dutyhours = frappe.db.sql("""
        SELECT COALESCE(SUM(custom_duty_hours),0)
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0

    doc.custom_duty_hours = total_dutyhours

    if doc.custom_overtime_hours == 0:
        frappe.msgprint(
            title="ℹ️ No Overtime Hours",
            msg=f"No overtime hours found for employee {doc.employee} in the selected period",
            indicator="blue"
        )
        return

    # ================================
    # 4 OVERTIME AMOUNT CALCULATION
    # ================================
    calculation_details = ""
    
    if employee.employment_type == "Permanent":
        adjusted_salary = base_salary * 0.85
        month_days = date_diff(doc.end_date, doc.start_date) + 1
        per_day_salary = adjusted_salary / month_days
        
        # Calculate overtime rate directly - NO intermediate rounding
        overtime_rate_raw = (per_day_salary / 8) * 1.5
        
        # Only round the final overtime rate
        doc.custom_overtime_rate = round_to_two_decimals(overtime_rate_raw)
        
        # Calculate amount using the rounded rate
        raw_amount = doc.custom_overtime_rate * doc.custom_overtime_hours
        doc.custom_overtime_amount = round_to_integer(raw_amount)
        
        calculation_details = f"""
        <b>Calculation Details (Permanent Employee):</b><br>
        Base Salary: {base_salary}<br>
        Adjusted Salary (85%): {adjusted_salary:.2f}<br>
        Month Days: {month_days}<br>
        Per Day Salary: {per_day_salary:.6f}<br>
        Overtime Rate (RAW - Direct Calculation): {overtime_rate_raw:.6f}<br>
        <b>Overtime Rate (Rounded to 2 decimals): {doc.custom_overtime_rate:.2f}</b><br>
        Total Overtime Hours: {doc.custom_overtime_hours}<br>
        Raw Amount (Rate × Hours): {raw_amount:.4f}<br>
        <b>Final Overtime Amount (Rounded): {doc.custom_overtime_amount}</b>
        """

    elif employee.employment_type == "Daily Wages":
        # Calculate overtime rate directly - NO intermediate rounding
        # DO NOT round per hour rate first!
        overtime_rate_raw = (base_salary / 8) * 1.5
        
        # Only round the final overtime rate
        doc.custom_overtime_rate = round_to_two_decimals(overtime_rate_raw)
        
        # Calculate amount using the rounded rate
        raw_amount = doc.custom_overtime_rate * doc.custom_overtime_hours
        doc.custom_overtime_amount = round_to_integer(raw_amount)
        
        calculation_details = f"""
        <b>Calculation Details (Daily Wages Employee):</b><br>
        Base Salary: {base_salary}<br>
        Overtime Rate (RAW - Direct Calculation): {overtime_rate_raw:.6f}<br>
        <b>Overtime Rate (Rounded to 2 decimals): {doc.custom_overtime_rate:.2f}</b><br>
        Total Overtime Hours: {doc.custom_overtime_hours}<br>
        Raw Amount (Rate × Hours): {raw_amount:.4f}<br>
        <b>Final Overtime Amount (Rounded): {doc.custom_overtime_amount}</b>
        """

    # ================================
    # 5 ROUND EARNINGS
    # ================================
    for row in doc.earnings:
        original_amount = row.amount
        row.amount = round_to_integer(original_amount)
        if original_amount != row.amount:
            calculation_details += f"<br>Rounded earning {row.salary_component}: {original_amount:.2f} → {row.amount}"

    # ================================
    # 6 GROSS PAY
    # ================================
    earnings_sum = sum(row.amount for row in doc.earnings)
    doc.gross_pay = earnings_sum + doc.custom_overtime_amount
    
    # ================================
    # 7 NET PAY
    # ================================
    doc.net_pay = doc.gross_pay - flt(doc.total_deduction)
    doc.rounded_total = round_to_integer(doc.net_pay)
    doc.total_in_words = money_in_words(doc.rounded_total)
    
    # Show popup with calculation details
    frappe.msgprint(
        title="✅ Overtime Calculated Successfully",
        msg=f"""
        <div style="font-family: monospace;">
        {calculation_details}
        
        <hr>
        <b>Summary:</b><br>
        Total Earnings (after rounding): {earnings_sum}<br>
        Overtime Amount: {doc.custom_overtime_amount}<br>
        Gross Pay: {doc.gross_pay}<br>
        Total Deduction: {flt(doc.total_deduction)}<br>
        Net Pay: {doc.net_pay:.2f}<br>
        <b>Final Rounded Total: {doc.rounded_total}</b><br>
        Amount in Words: {doc.total_in_words}
        </div>
        """,
        indicator="green",
        alert=True
    )