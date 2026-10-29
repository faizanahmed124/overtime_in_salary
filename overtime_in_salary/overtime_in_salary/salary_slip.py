import frappe
from frappe.utils import date_diff, flt, money_in_words
from decimal import Decimal, ROUND_HALF_UP

from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip


def round_to_two_decimals(value):
    d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(d)


def round_to_integer(value):
    d = Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(d)

def set_working_and_payment_days(doc):
    """Working Days = days actually present (half day = 0.5).
    Leave With Pay = approved paid-leave days (non-LWP leave types).
    Payment Days = Working Days + Leave With Pay."""
    row = frappe.db.sql("""
        SELECT
            COALESCE(SUM(CASE
                WHEN a.status IN ('Present', 'Work From Home') THEN 1
                WHEN a.status = 'Half Day' THEN 0.5
                ELSE 0 END), 0),
            COALESCE(SUM(CASE
                WHEN a.status = 'On Leave' AND COALESCE(lt.is_lwp, 0) = 0 THEN 1
                WHEN a.status = 'Half Day' AND a.leave_type IS NOT NULL AND a.leave_type != ''
                     AND COALESCE(lt.is_lwp, 0) = 0 THEN 0.5
                ELSE 0 END), 0)
        FROM `tabAttendance` a
        LEFT JOIN `tabLeave Type` lt ON lt.name = a.leave_type
        WHERE a.employee=%s
        AND a.attendance_date BETWEEN %s AND %s
        AND a.docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0]

    doc.total_working_days = flt(row[0])
    doc.custom_leave_with_pay = flt(row[1])
    doc.payment_days = doc.total_working_days + doc.custom_leave_with_pay

def apply_employee_eobi(doc, employee):
    """The Employee form (EOBI Applicable + EOBI Amount) is the source of truth for EOBI.
    Structures are shared between employees, so the slip's EOBI deduction is aligned here:
    not applicable -> 0, applicable -> the employee's amount (row added if the structure lacks it)."""
    target = flt(employee.custom_eobi_amount) if employee.custom_eobi_applicable else 0

    rows = [r for r in doc.get("deductions") if "EOBI" in (r.salary_component or "").upper()]
    if not rows:
        if not target or not frappe.db.exists("Salary Component", "EOBI"):
            return
        row = doc.append(
            "deductions",
            {"salary_component": "EOBI", "abbr": frappe.db.get_value("Salary Component", "EOBI", "salary_component_abbr")},
        )
        rows = [row]
        row.amount = 0

    # one EOBI deduction per slip: the first row carries the amount, duplicates are zeroed
    for i, row in enumerate(rows):
        new_amount = target if i == 0 else 0
        delta = flt(new_amount) - flt(row.amount)
        row.amount = new_amount
        row.default_amount = new_amount
        row.additional_amount = 0
        if delta and not row.get("do_not_include_in_total"):
            doc.total_deduction = flt(doc.total_deduction) + delta
            doc.base_total_deduction = flt(doc.get("base_total_deduction")) + delta * flt(doc.get("exchange_rate") or 1)

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
    apply_employee_eobi(doc, employee)
    income_tax_amount = flt(employee.custom_income_tax_amount) or 0
    emp_type = (employee.employment_type or "").upper().strip()
    is_permanent = emp_type == "PERMANENT"

    # ================================
    # HELPER: only rows that count in ERPNext totals
    # (rows flagged "do not include in total" must never change pay)
    # ================================
    def counted_earnings_sum():
        return sum(
            flt(row.amount) for row in doc.earnings if not row.get("do_not_include_in_total")
        )

    def round_all_earnings():
        for row in doc.earnings:
            row.amount = round_to_integer(row.amount)

    # ================================
    # HELPER: finalize pay
    # ================================
    def finalize_pay(earnings_sum, gross_pay=None, overtime_amount=0, is_permanent=False):
        if gross_pay is None:
            gross_pay = earnings_sum

        doc.gross_pay = gross_pay

        doc.custom_total_earnings = flt(doc.gross_pay)   # shown as Total Earnings in print
        loan_repayment = flt(doc.get("total_loan_repayment"))   # ERPNext deducts this from net pay

        if is_permanent:
            doc.total_deduction = flt(doc.total_deduction) + income_tax_amount + flt(doc.custom_less_duty_hours_amount or 0)
            doc.net_pay = round_to_integer(doc.gross_pay - doc.total_deduction - loan_repayment)
            doc.custom_paid_salary = doc.net_pay + overtime_amount
            doc.rounded_total = round_to_integer(doc.custom_paid_salary)
            doc.custom_per_day_rate = flt(employee.ctc) or 0
        else:
            doc.total_deduction = flt(doc.total_deduction) + income_tax_amount
            doc.net_pay = round_to_integer(doc.gross_pay - doc.total_deduction - loan_repayment)
            doc.custom_paid_salary = doc.net_pay
            doc.rounded_total = round_to_integer(doc.net_pay)

        doc.total_in_words = money_in_words(doc.rounded_total)

    # ================================
    # 1 GET BASE SALARY
    # ================================
    base_salary = flt(
        frappe.db.get_value(
            "Salary Structure Assignment",
            {
                "employee": doc.employee,
                "docstatus": 1,
                "from_date": ["<=", doc.start_date]
            },
            "base",
            order_by="from_date DESC"
        )
    )

    if emp_type == "DAILY WAGES":
        doc.custom_per_day_rate = flt(base_salary, 2)

    month_days = date_diff(doc.end_date, doc.start_date) + 1

    # ================================
    # 2 DUTY HOURS (informational)
    # ================================
    doc.custom_duty_hours = frappe.db.sql("""
        SELECT COALESCE(SUM(custom_duty_hours),0)
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND docstatus=1
    """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0

    set_working_and_payment_days(doc)

    # ================================
    # 3 HALF DAYS
    # Half days that ERPNext already prorated (half_day_status=Absent, or
    # linked to a leave type) are already reflected in earnings, so only the
    # remaining ones are deducted here (no double deduction). Payment days
    # already count every half day as 0.5 (see set_working_and_payment_days).
    # ================================
    half_day_rows = frappe.db.sql("""
        SELECT name
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND status='Half Day'
        AND docstatus=1
        AND COALESCE(half_day_status,'') != 'Absent'
        AND COALESCE(leave_type,'') = ''
    """, (doc.employee, doc.start_date, doc.end_date))
    half_day_count = len(half_day_rows)
    half_day_deduction = 0

    if half_day_count > 0 and base_salary > 0:
        per_day = base_salary / month_days
        half_day_deduction = round_to_integer(per_day * 0.5 * half_day_count)

        if doc.earnings:
            doc.earnings[0].amount = max(
                0, round_to_integer(flt(doc.earnings[0].amount) - half_day_deduction)
            )

    # ================================
    # 4 OVERTIME / LESS DUTY HOURS (hours)
    # Half Day attendance is excluded from both: it is already paid at half
    # salary above, and its auto-generated 7.5 "less duty hours" would
    # otherwise deduct the same time a second time.
    # ================================
    overtime_allowed = bool(employee.custom_allow_overtime)

    total_overtime = 0
    if overtime_allowed:
        total_overtime = flt(frappe.db.sql("""
            SELECT COALESCE(SUM(custom_overtime),0)
            FROM `tabAttendance`
            WHERE employee=%s
            AND attendance_date BETWEEN %s AND %s
            AND docstatus=1
            AND status != 'Half Day'
        """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0)

    ldh = 0
    if is_permanent:
        ldh = flt(frappe.db.sql("""
            SELECT COALESCE(SUM(custom_less_duty_hour),0)
            FROM `tabAttendance`
            WHERE employee=%s
            AND attendance_date BETWEEN %s AND %s
            AND docstatus=1
            AND status != 'Half Day'
        """, (doc.employee, doc.start_date, doc.end_date))[0][0] or 0)

        # LDH vs overtime adjustment (overtime offsets less duty hours)
        if total_overtime > ldh:
            total_overtime = round(total_overtime - ldh, 2)
            ldh = 0
        elif ldh > total_overtime:
            ldh = round(ldh - total_overtime, 2)
            total_overtime = 0
        else:
            total_overtime = 0
            ldh = 0

        if ldh > 0 and base_salary > 0:
            per_hour_rate = (base_salary / month_days) / 8
            doc.custom_less_duty_hours_amount = round_to_two_decimals(per_hour_rate * ldh)

    doc.custom_overtime_hours = total_overtime
    doc.custom_less_duty_hour = ldh

    # ── Nothing overtime-related to add: just finalize ──
    if base_salary == 0 or total_overtime == 0:
        round_all_earnings()
        finalize_pay(counted_earnings_sum(), is_permanent=is_permanent)
        if not overtime_allowed:
            msg = f"Employee {doc.employee} does not have overtime enabled."
            title, indicator = "⚠️ Overtime Not Allowed", "orange"
        elif base_salary == 0:
            msg = f"No salary structure found for {doc.employee}."
            title, indicator = "⚠️ No Base Salary", "red"
        else:
            msg = f"No overtime hours found for {doc.employee} in this period."
            title, indicator = "ℹ️ No Overtime Hours", "blue"
        frappe.msgprint(
            title=title,
            msg=f"{msg}<br>Half Days: {half_day_count} → Deduction: -{half_day_deduction}"
                f"<br>Less Duty Hours: {doc.custom_less_duty_hour} → Deduction: -{doc.custom_less_duty_hours_amount}"
                f"<br><b>Income Tax {income_tax_amount} added to deduction.</b>",
            indicator=indicator
        )
        return

    # ================================
    # 4 OVERTIME CALCULATION
    # ================================
    calculation_details = ""

    if emp_type == "PERMANENT":
        adjusted_salary = round_to_integer(base_salary * 0.85)
        per_day_salary = adjusted_salary / month_days
        overtime_rate_raw = (per_day_salary / 8) * 1.5
        doc.custom_overtime_rate = round_to_two_decimals(overtime_rate_raw)
        raw_amount = doc.custom_overtime_rate * doc.custom_overtime_hours
        doc.custom_overtime_amount = round_to_integer(raw_amount)

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
        finalize_pay(counted_earnings_sum())
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
    earnings_sum = counted_earnings_sum()

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


class CustomSalarySlip(SalarySlip):
    """Standard HRMS Salary Slip + custom overtime / less-duty logic.

    Every original method (validate, calculate_net_pay, tax, loans, LWP,
    timesheets, emailing, status, etc.) is inherited untouched.
    """

    def validate(self):
        # Run the full original validation + calculation first
        super().validate()

        # Then apply the custom overtime logic exactly once
        if not self.flags.get("custom_overtime_done"):
            calculate_overtime(self, "validate")
            self.flags.custom_overtime_done = True

            # keep the derived month/year-to-date figures in line with the final net pay
            self.compute_year_to_date()
            self.compute_month_to_date()
            self.compute_component_wise_year_to_date()
