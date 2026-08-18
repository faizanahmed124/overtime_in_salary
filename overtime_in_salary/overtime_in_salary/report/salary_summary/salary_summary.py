import re
import frappe
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        filters = {}
    records, earn_comps, ded_comps = get_data(filters)
    columns = get_columns(records, earn_comps, ded_comps)
    chart   = get_chart(records)
    summary = get_report_summary(records)
    return columns, records, None, chart, summary


# ─────────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────────
def _safe_fn(prefix, name):
    """Salary component name → safe fieldname  e.g. 'Basic Pay' → 'e_basic_pay'"""
    return (prefix + re.sub(r"[^a-z0-9]", "_", name.lower().strip()))[:52]


HOUSE_STAFF_BRANCH = "ATS HOUSE "

def _build_conditions(filters):
    cond = "ss.docstatus = 1"
    if filters.get("company"):
        cond += " AND ss.company = %(company)s"
    if filters.get("from_date"):
        cond += " AND ss.start_date >= %(from_date)s"
    if filters.get("to_date"):
        cond += " AND ss.end_date <= %(to_date)s"
    if filters.get("branch"):
        # Specific branch selected — show only that branch
        cond += " AND ss.branch = %(branch)s"
    else:
        # No branch selected — exclude ATS HOUSE  automatically
        cond += f" AND ss.branch != '{HOUSE_STAFF_BRANCH}'"
    if filters.get("employment_type"):
        cond += " AND e.employment_type = %(employment_type)s"
    if filters.get("mode_of_payment"):
        cond += " AND ss.mode_of_payment = %(mode_of_payment)s"
    return cond


# ─────────────────────────────────────────────────────────────────
# COLUMNS  — fully dynamic based on actual components in data
# ─────────────────────────────────────────────────────────────────
def get_columns(records, earn_comps, ded_comps):
    check = [r for r in records if "<b>Grand Total</b>" not in (r.get("department") or "")]

    def has_val(fn):
        return any(flt(r.get(fn)) for r in check)

    cols = [
        {"label": "Department", "fieldname": "department",
         "fieldtype": "Link", "options": "Department", "width": 200},
        {"label": "No. of Emp", "fieldname": "total_employees",
         "fieldtype": "Int", "width": 90},
    ]

    # ── All Earnings ──────────────────────────────────────────────
    for comp in earn_comps:
        fn = _safe_fn("e_", comp)
        if has_val(fn):
            cols.append({"label": comp, "fieldname": fn,
                         "fieldtype": "Currency", "width": 140, "precision": 0})

    # Custom Allowance (earning — custom field on Salary Slip)
    cols.append({"label": "Allowance", "fieldname": "custom_allowance",
                 "fieldtype": "Currency", "width": 130, "precision": 0})

    # OT Amount (custom field on Salary Slip)
    if has_val("ot_amount"):
        cols.append({"label": "OT Amount", "fieldname": "ot_amount",
                     "fieldtype": "Currency", "width": 130, "precision": 0})

    # Gross total
    cols.append({"label": "Gross Salary", "fieldname": "gross_salary",
                 "fieldtype": "Currency", "width": 150, "precision": 0})

    # ── All Deductions ────────────────────────────────────────────
    for comp in ded_comps:
        fn = _safe_fn("d_", comp)
        if has_val(fn):
            cols.append({"label": comp, "fieldname": fn,
                         "fieldtype": "Currency", "width": 130, "precision": 0})

    # Custom Income Tax (deduction — custom field on Salary Slip)
    cols.append({"label": "Income Tax", "fieldname": "custom_income_tax",
                 "fieldtype": "Currency", "width": 130, "precision": 0})

    # Less Duty Hours deduction
    if has_val("less_duty_hours"):
        cols.append({"label": "Less Duty Hrs", "fieldname": "less_duty_hours",
                     "fieldtype": "Currency", "width": 130, "precision": 0})

    # Net total
    cols.append({"label": "Paid Salary", "fieldname": "net_salary",
                 "fieldtype": "Currency", "width": 150, "precision": 0})

    return cols


# ─────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────
def get_data(filters):
    cond = _build_conditions(filters)

    # ── 1. Base department totals ─────────────────────────────────
    base = frappe.db.sql(
        f"""
        SELECT
            IFNULL(e.department, '— No Department —')   AS department,
            COUNT(DISTINCT ss.employee)                  AS total_employees,
            SUM(IFNULL(ss.custom_overtime_amount, 0))        AS ot_amount,
            SUM(IFNULL(ss.custom_allowance, 0))              AS custom_allowance,
            SUM(IFNULL(ss.gross_pay, 0))                     AS gross_salary,
            SUM(IFNULL(ss.total_deduction, 0))               AS total_deductions,
            SUM(IFNULL(ss.custom_incone_tax_amount, 0))         AS custom_income_tax,
            SUM(IFNULL(ss.custom_less_duty_hours_amount, 0))    AS less_duty_hours,
            SUM(IFNULL(NULLIF(ss.rounded_total,0), ss.net_pay)) AS net_salary
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE {cond}
        GROUP BY IFNULL(e.department, '— No Department —')
        ORDER BY IFNULL(e.department, '') ASC
        """,
        filters,
        as_dict=True,
    )

    if not base:
        return [], [], []

    # ── 2. All salary components per department (one query) ───────
    comp_rows = frappe.db.sql(
        f"""
        SELECT
            IFNULL(e.department, '— No Department —')  AS department,
            sd.salary_component,
            sd.parentfield,
            SUM(sd.amount)                             AS amount
        FROM `tabSalary Detail` sd
        JOIN  `tabSalary Slip` ss ON ss.name = sd.parent
        LEFT JOIN `tabEmployee` e  ON e.name  = ss.employee
        WHERE {cond}
          AND sd.amount > 0
        GROUP BY IFNULL(e.department, '— No Department —'),
                 sd.salary_component, sd.parentfield
        ORDER BY sd.parentfield DESC, sd.salary_component ASC
        """,
        filters,
        as_dict=True,
    )

    # ── 3. Collect unique component lists (in order seen) ─────────
    earn_comps, ded_comps = [], []
    seen_e, seen_d = set(), set()
    for c in comp_rows:
        if c.parentfield == "earnings" and c.salary_component not in seen_e:
            earn_comps.append(c.salary_component)
            seen_e.add(c.salary_component)
        elif c.parentfield == "deductions" and c.salary_component not in seen_d:
            ded_comps.append(c.salary_component)
            seen_d.add(c.salary_component)

    # ── 4. dept → component → amount lookup ──────────────────────
    dept_comp = {}
    for c in comp_rows:
        dept_comp.setdefault(c.department, {})[(c.salary_component, c.parentfield)] = flt(c.amount)

    # ── 5. Enrich base records ────────────────────────────────────
    for r in base:
        d = r.department
        for comp in earn_comps:
            r[_safe_fn("e_", comp)] = flt(dept_comp.get(d, {}).get((comp, "earnings"), 0))
        for comp in ded_comps:
            r[_safe_fn("d_", comp)] = flt(dept_comp.get(d, {}).get((comp, "deductions"), 0))

    # ── 6. Grand Total ────────────────────────────────────────────
    grand = {
        "department":       "<b>Grand Total</b>",
        "total_employees":  sum(r.total_employees or 0  for r in base),
        "ot_amount":          sum(flt(r.ot_amount)          for r in base),
        "custom_allowance":   sum(flt(r.custom_allowance)   for r in base),
        "gross_salary":       sum(flt(r.gross_salary)       for r in base),
        "total_deductions":   sum(flt(r.total_deductions)   for r in base),
        "custom_income_tax":  sum(flt(r.custom_income_tax)  for r in base),
        "less_duty_hours":    sum(flt(r.less_duty_hours)    for r in base),
        "net_salary":         sum(flt(r.net_salary)         for r in base),
    }
    for comp in earn_comps:
        fn = _safe_fn("e_", comp)
        grand[fn] = sum(flt(r.get(fn)) for r in base)
    for comp in ded_comps:
        fn = _safe_fn("d_", comp)
        grand[fn] = sum(flt(r.get(fn)) for r in base)

    base.append(grand)
    return base, earn_comps, ded_comps


# ─────────────────────────────────────────────────────────────────
# CHART
# ─────────────────────────────────────────────────────────────────
def get_chart(data):
    rows = [r for r in data if "<b>Grand Total</b>" not in (r.get("department") or "")]
    if not rows:
        return None

    datasets = [
        {"name": "Gross Salary", "values": [flt(r.get("gross_salary")) for r in rows]},
        {"name": "Paid Salary",  "values": [flt(r.get("net_salary"))   for r in rows]},
    ]
    if any(flt(r.get("ot_amount")) for r in rows):
        datasets.insert(0, {"name": "OT Amount", "values": [flt(r.get("ot_amount")) for r in rows]})

    return {
        "data":       {"labels": [r.get("department") or "—" for r in rows], "datasets": datasets},
        "type":       "bar",
        "colors":     ["#F4A25E", "#38BDF8", "#5EF4A2"],
        "barOptions": {"stacked": False, "spaceRatio": 0.3},
        "height":     280,
    }


# ─────────────────────────────────────────────────────────────────
# REPORT SUMMARY  (KPI cards)
# ─────────────────────────────────────────────────────────────────
def get_report_summary(data):
    grand = next((r for r in data if "<b>Grand Total</b>" in (r.get("department") or "")), None)
    if not grand:
        return None

    currency = frappe.defaults.get_global_default("currency") or "PKR"

    def card(value, label, dtype, indicator, curr=None):
        c = {"value": value, "label": label, "datatype": dtype, "indicator": indicator}
        if curr:
            c["currency"] = curr
        return c

    summary = [card(grand.get("total_employees", 0), "Total Employees", "Int", "blue")]

    base_amt = flt(grand.get("gross_salary")) - flt(grand.get("ot_amount"))
    if base_amt:
        summary.append(card(base_amt, "Total Amount", "Currency", "blue", currency))
    if flt(grand.get("ot_amount")):
        summary.append(card(flt(grand.get("ot_amount")), "OT Amount", "Currency", "orange", currency))

    summary.append(card(flt(grand.get("gross_salary")),     "Gross Salary",      "Currency", "green",  currency))
    summary.append(card(flt(grand.get("total_deductions")), "Total Deductions",  "Currency", "red",    currency))
    summary.append(card(flt(grand.get("net_salary")),       "Paid Salary",       "Currency", "green",  currency))

    return summary