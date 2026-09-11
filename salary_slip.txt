import frappe
from frappe.utils import date_diff, flt, money_in_words
from decimal import Decimal, ROUND_HALF_UP

def round_to_two_decimals(value):
    d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(d)

def round_to_integer(value):
    d = Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(d)

def calculate_overtime(doc, method):
    # Initialize fields
    doc.custom_overtime_hours = 0
    doc.custom_overtime_amount = 0
    doc.custom_per_day_rate = 0
    doc.custom_overtime_rate = 0
    doc.custom_duty_hours = 0
    doc.custom_less_duty_hour = 0
    doc.custom_less_duty_hours_amount = 0

    if not doc.employee or not doc.start_date or not doc.end_date:
        frappe.msgprint(
            title="⚠️ Skipped",
            msg="Missing employee, start date, or end date",
            indicator="orange"
        )
        return

    employee = frappe.get_doc("Employee", doc.employee)
    income_tax_amount = flt(employee.custom_income_tax_amount) or 0
    emp_type = (employee.employment_type or "").upper().strip()

    # ================================
    # HELPER: round all earning rows
    # ================================
    def round_all_earnings():
        for row in doc.earnings:
            row.amount = round_to_integer(row.amount)

    # ================================
    # HELPER: finalize pay
    # ================================
    def finalize_pay(earnings_sum, gross_pay=None, overtime_amount=0, is_permanent=False):
        if gross_pay is None:
            gross_pay = earnings_sum

        doc.gross_pay = gross_pay   # ✅ allowance yahan include nahi hota

        allowance = flt(doc.custom_allowance or 0)

        if is_permanent:
            doc.total_deduction = flt(doc.total_deduction) + income_tax_amount + flt(doc.custom_less_duty_hours_amount or 0)
            doc.net_pay = round_to_integer(doc.gross_pay - doc.total_deduction + allowance)  # ✅ allowance yahan add
            doc.custom_paid_salary = doc.net_pay + overtime_amount
            doc.rounded_total = round_to_integer(doc.custom_paid_salary)
            doc.custom_per_day_rate = flt(employee.ctc) or 0
        else:
            doc.total_deduction = flt(doc.total_deduction) + income_tax_amount
            doc.net_pay = round_to_integer(doc.gross_pay - doc.total_deduction + allowance)  # ✅ allowance yahan add
            doc.custom_paid_salary = doc.net_pay
            doc.rounded_total = round_to_integer(doc.net_pay)

        doc.total_in_words = money_in_words(doc.rounded_total)

    # ── Check overtime allowed ──
    if not employee.custom_allow_overtime:
        round_all_earnings()
        earnings_sum = sum(row.amount for row in doc.earnings)
        finalize_pay(earnings_sum, is_permanent=(emp_type == "PERMANENT"))
        frappe.msgprint(
            title="⚠️ Overtime Not Allowed",
            msg=f"Employee {doc.employee} does not have overtime enabled.<br><b>Income Tax {income_tax_amount} added to deduction.</b>",
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

    if emp_type == "DAILY WAGES":
        doc.custom_per_day_rate = flt(base_salary, 2)

    if base_salary == 0:
        round_all_earnings()
        earnings_sum = sum(row.amount for row in doc.earnings)
        finalize_pay(earnings_sum, is_permanent=(emp_type == "PERMANENT"))
        frappe.msgprint(
            title="⚠️ No Base Salary",
            msg=f"No salary structure found for {doc.employee}.<br><b>Income Tax {income_tax_amount} added to deduction.</b>",
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

    # ================================
    # 3.7, 3.8, 3.9 — ONLY FOR PERMANENT
    # ================================
    if emp_type == "PERMANENT":

        # ================================
        # 3.7 TOTAL LESS DUTY HOURS
        # ================================
        total_less_duty_hours = frappe.db.sql("""
            SELECT COALESCE(SUM(custom_less_duty_hour),0)
            FROM `tabAttendance`
            WHERE employee=%s
            AND attendance_date BETWEEN %s AND %s
            AND docstatus=1
        """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0

        doc.custom_less_duty_hour = flt(total_less_duty_hours)

        # ================================
        # 3.8 LDH vs OVERTIME ADJUSTMENT
        # ================================
        ldh = flt(doc.custom_less_duty_hour)
        ot  = flt(doc.custom_overtime_hours)

        if ot > ldh:
            doc.custom_overtime_hours = round(ot - ldh, 2)
            doc.custom_less_duty_hour = 0
        elif ldh > ot:
            doc.custom_less_duty_hour = round(ldh - ot, 2)
            doc.custom_overtime_hours = 0
        else:
            doc.custom_overtime_hours = 0
            doc.custom_less_duty_hour = 0

        # ================================
        # 3.9 LDH AMOUNT CALCULATION
        # ================================
        if doc.custom_less_duty_hour > 0:
            month_days    = date_diff(doc.end_date, doc.start_date) + 1
            per_day_rate  = flt(base_salary) / month_days
            per_hour_rate = per_day_rate / 8
            doc.custom_less_duty_hours_amount = round_to_two_decimals(
                per_hour_rate * doc.custom_less_duty_hour
            )
        else:
            doc.custom_less_duty_hours_amount = 0

    # ================================
    # 3.5 HALF DAY COUNT & PAYMENT DAYS ADJUST
    # ================================
    half_day_count = frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND status='Half Day'
        AND docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0

    half_day_deduction = 0

    if half_day_count > 0:
        doc.payment_days = flt(doc.payment_days) - (half_day_count * 0.5)

        month_days = date_diff(doc.end_date, doc.start_date) + 1
        per_day = flt(base_salary) / month_days
        half_day_deduction = round_to_integer(per_day * 0.5 * half_day_count)

        if doc.earnings:
            doc.earnings[0].amount = round_to_integer(
                flt(doc.earnings[0].amount) - half_day_deduction
            )

    if doc.custom_overtime_hours == 0:
        round_all_earnings()
        earnings_sum = sum(row.amount for row in doc.earnings)
        finalize_pay(earnings_sum, is_permanent=(emp_type == "PERMANENT"))
        frappe.msgprint(
            title="ℹ️ No Overtime Hours",
            msg=f"No overtime hours found for {doc.employee} in this period.<br><b>Income Tax {income_tax_amount} added to deduction.</b>",
            indicator="blue"
        )
        return

    # ================================
    # 4 OVERTIME CALCULATION
    # ================================
    calculation_details = ""

    if emp_type == "PERMANENT":
        adjusted_salary = round_to_integer(base_salary * 0.85)
        month_days = date_diff(doc.end_date, doc.start_date) + 1
        per_day_salary = adjusted_salary / month_days
        overtime_rate_raw = (per_day_salary / 8) * 1.5
        doc.custom_overtime_rate = round_to_two_decimals(overtime_rate_raw)
        raw_amount = doc.custom_overtime_rate * doc.custom_overtime_hours
        doc.custom_overtime_amount = round(raw_amount)

        calculation_details = f"""
        <b>Permanent Employee:</b><br>
        Base Salary: {base_salary}<br>
        CTC: {flt(employee.ctc)}<br>
        Adjusted (85%): {adjusted_salary:.2f}<br>
        Month Days: {month_days}<br>
        Per Day: {per_day_salary:.6f}<br>
        OT Rate: {doc.custom_overtime_rate:.2f}<br>
        OT Hours (after LDH adj): {doc.custom_overtime_hours}<br>
        <b>OT Amount: {doc.custom_overtime_amount}</b><br>
        <hr>
        Less Duty Hours (after adj): {doc.custom_less_duty_hour}<br>
        LDH Amount: {doc.custom_less_duty_hours_amount}<br>
        """

    elif emp_type == "DAILY WAGES":
        overtime_rate_raw = (base_salary / 8) * 1.5
        doc.custom_overtime_rate = round_to_two_decimals(overtime_rate_raw)
        raw_amount = doc.custom_overtime_rate * doc.custom_overtime_hours
        doc.custom_overtime_amount = round_to_integer(raw_amount)

        calculation_details = f"""
        <b>Daily Wages Employee:</b><br>
        Base Salary: {base_salary}<br>
        OT Rate: {doc.custom_overtime_rate:.2f}<br>
        OT Hours: {doc.custom_overtime_hours}<br>
        <b>OT Amount: {doc.custom_overtime_amount}</b>
        """

    else:
        frappe.msgprint(
            title="⚠️ Employment Type Not Matched",
            msg=f"Employment Type in DB: <b>'{employee.employment_type}'</b><br>Expected: 'PERMANENT' or 'DAILY WAGES'",
            indicator="red"
        )
        round_all_earnings()
        earnings_sum = sum(row.amount for row in doc.earnings)
        finalize_pay(earnings_sum)
        return

    # ================================
    # 5 ROUND EARNINGS
    # ================================
    for row in doc.earnings:
        original_amount = row.amount
        row.amount = round_to_integer(original_amount)
        if original_amount != row.amount:
            calculation_details += f"<br>Rounded {row.salary_component}: {original_amount:.2f} → {row.amount}"

    # ================================
    # 6 GROSS PAY
    # ================================
    earnings_sum = sum(row.amount for row in doc.earnings)

    if emp_type == "PERMANENT":
        gross_pay = earnings_sum
    else:
        gross_pay = earnings_sum + doc.custom_overtime_amount

    # ================================
    # 7 FINALIZE
    # ================================
    finalize_pay(
        earnings_sum=earnings_sum,
        gross_pay=gross_pay,
        overtime_amount=doc.custom_overtime_amount,
        is_permanent=(emp_type == "PERMANENT")
    )

    frappe.msgprint(
        title="✅ Overtime Calculated",
        msg=f"""
        <div style="font-family: monospace;">
        {calculation_details}
        <hr>
        Employment Type: {employee.employment_type}<br>
        Half Days: {half_day_count} → Deduction: -{half_day_deduction}<br>
        Payment Days: {doc.payment_days}<br>
        Earnings Sum: {earnings_sum}<br>
        Allowance (added to Net Pay): {flt(doc.custom_allowance or 0)}<br>
        OT Amount: {doc.custom_overtime_amount}<br>
        Gross Pay: {doc.gross_pay}<br>
        Pay Rate (CTC): {doc.custom_per_day_rate}<br>
        Total Deduction (incl. Tax {income_tax_amount}): {doc.total_deduction}<br>
        Net Pay: {doc.net_pay}<br>
        {"<b>Custom Paid Salary (Net + OT): " + str(doc.custom_paid_salary) + "</b><br>" if emp_type == "PERMANENT" else ""}
        Rounded Total: {doc.rounded_total}<br>
        In Words: {doc.total_in_words}
        </div>
        """,
        indicator="green"
    )