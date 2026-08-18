import frappe
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        filters = {}
    data    = get_data(filters)
    columns = get_columns(data)      # dynamic — hides zero columns
    chart   = get_chart(data)
    summary = get_report_summary(data)
    return columns, data, None, chart, summary


# ─────────────────────────────────────────────────────────────────
# COLUMNS  — dynamic: only show columns that have non-zero data
# ─────────────────────────────────────────────────────────────────
def get_columns(data):
    # Exclude grand-total row when checking for non-zero values
    check_rows = [
        r for r in data
        if "<b>Grand Total</b>" not in (r.get("department") or "")
    ]

    def has_value(field):
        return any(flt(r.get(field)) for r in check_rows)

    # Always visible
    cols = [
        {
            "label":     "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options":   "Department",
            "width":     200,
        },
        {
            "label":     "No. of Emp",
            "fieldname": "total_employees",
            "fieldtype": "Int",
            "width":     100,
        },
    ]

    # Optional columns — only added if they have any non-zero value
    optional = [
        ("Amount",       "amount",       "Currency", 140),
        ("OT Amount",    "ot_amount",    "Currency", 130),
        ("Gross Salary", "gross_salary", "Currency", 150),
        ("Allowance",    "allowance",    "Currency", 130),
        ("EOBI",         "eobi",         "Currency", 110),
        ("Income Tax",   "income_tax",   "Currency", 120),
        ("Net Salary",   "net_salary",   "Currency", 150),
    ]

    for label, fieldname, fieldtype, width in optional:
        if has_value(fieldname):
            col = {
                "label":     label,
                "fieldname": fieldname,
                "fieldtype": fieldtype,
                "width":     width,
            }
            cols.append(col)

    return cols


# ─────────────────────────────────────────────────────────────────
# DATA  (GROUP BY department)
# ─────────────────────────────────────────────────────────────────
def get_data(filters):
    conditions = "ss.docstatus = 1"

    if filters.get("department"):
        conditions += " AND e.department = %(department)s"
    if filters.get("from_date"):
        conditions += " AND ss.start_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND ss.end_date <= %(to_date)s"
    if filters.get("company"):
        conditions += " AND ss.company = %(company)s"
    if filters.get("branch"):
        conditions += " AND ss.branch = %(branch)s"
    if filters.get("mode_of_payment"):
        conditions += " AND ss.mode_of_payment = %(mode_of_payment)s"

    records = frappe.db.sql(
        f"""
        SELECT
            IFNULL(e.department, '— No Department —')      AS department,
            COUNT(DISTINCT ss.employee)                     AS total_employees,
            SUM(IFNULL(ss.gross_pay, 0)
                - IFNULL(ss.custom_overtime_amount, 0))    AS amount,
            SUM(IFNULL(ss.custom_overtime_hours, 0))        AS ot_hours,
            SUM(IFNULL(ss.custom_overtime_amount, 0))       AS ot_amount,
            SUM(IFNULL(ss.gross_pay, 0))                    AS gross_salary,
            SUM(IFNULL(ss.net_pay, 0))                      AS net_salary,
            GROUP_CONCAT(ss.name)                           AS slip_names_csv
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE {conditions}
        GROUP BY IFNULL(e.department, '— No Department —')
        ORDER BY IFNULL(e.department, '') ASC
        """,
        filters,
        as_dict=True,
    )

    if not records:
        return []

    # ── Fetch Allowance / EOBI / Income Tax per department ────────
    all_slips     = []
    dept_slip_map = {}

    for r in records:
        slips = r.slip_names_csv.split(",") if r.slip_names_csv else []
        dept_slip_map[r.department] = slips
        all_slips.extend(slips)

    if all_slips:
        comp_rows = frappe.db.sql(
            """
            SELECT parent, salary_component, SUM(amount) AS amount
            FROM   `tabSalary Detail`
            WHERE  parent           IN %(slips)s
              AND  salary_component IN ('Allowance', 'EOBI', 'Income Tax')
            GROUP  BY parent, salary_component
            """,
            {"slips": all_slips},
            as_dict=True,
        )

        slip_comp = {}
        for c in comp_rows:
            slip_comp.setdefault(c.parent, {})[c.salary_component] = flt(c.amount)

        for r in records:
            slips        = dept_slip_map.get(r.department, [])
            r.allowance  = sum(flt(slip_comp.get(s, {}).get("Allowance",  0)) for s in slips)
            r.eobi       = sum(flt(slip_comp.get(s, {}).get("EOBI",       0)) for s in slips)
            r.income_tax = sum(flt(slip_comp.get(s, {}).get("Income Tax", 0)) for s in slips)
    else:
        for r in records:
            r.allowance = r.eobi = r.income_tax = 0

    # ── Grand Total ───────────────────────────────────────────────
    records.append({
        "department":      "<b>Grand Total</b>",
        "total_employees": sum(r.total_employees or 0 for r in records),
        "amount":          sum(flt(r.amount)          for r in records),
        "ot_hours":        sum(flt(r.ot_hours)        for r in records),
        "ot_amount":       sum(flt(r.ot_amount)       for r in records),
        "gross_salary":    sum(flt(r.gross_salary)    for r in records),
        "allowance":       sum(flt(r.allowance)       for r in records),
        "eobi":            sum(flt(r.eobi)            for r in records),
        "income_tax":      sum(flt(r.income_tax)      for r in records),
        "net_salary":      sum(flt(r.net_salary)      for r in records),
    })

    return records


# ─────────────────────────────────────────────────────────────────
# CHART
# ─────────────────────────────────────────────────────────────────
def get_chart(data):
    rows = [
        r for r in data
        if "<b>Grand Total</b>" not in (r.get("department") or "")
    ]
    if not rows:
        return None

    datasets = []
    if any(flt(r.get("amount"))       for r in rows):
        datasets.append({"name": "Amount",       "values": [flt(r.get("amount"))       for r in rows]})
    if any(flt(r.get("ot_amount"))    for r in rows):
        datasets.append({"name": "OT Amount",    "values": [flt(r.get("ot_amount"))    for r in rows]})
    if any(flt(r.get("gross_salary")) for r in rows):
        datasets.append({"name": "Gross Salary", "values": [flt(r.get("gross_salary")) for r in rows]})
    if any(flt(r.get("net_salary"))   for r in rows):
        datasets.append({"name": "Net Salary",   "values": [flt(r.get("net_salary"))   for r in rows]})

    return {
        "data": {
            "labels":   [r.get("department") or "—" for r in rows],
            "datasets": datasets,
        },
        "type":       "bar",
        "colors":     ["#5E81F4", "#F4A25E", "#38BDF8", "#5EF4A2"],
        "barOptions": {"stacked": False, "spaceRatio": 0.3},
        "height":     280,
    }


# ─────────────────────────────────────────────────────────────────
# REPORT SUMMARY  (KPI cards — only non-zero)
# ─────────────────────────────────────────────────────────────────
def get_report_summary(data):
    grand = next(
        (r for r in data if "<b>Grand Total</b>" in (r.get("department") or "")),
        None,
    )
    if not grand:
        return None

    currency = frappe.defaults.get_global_default("currency") or "PKR"

    def card(value, label, dtype, indicator, curr=None):
        c = {"value": value, "label": label, "datatype": dtype, "indicator": indicator}
        if curr:
            c["currency"] = curr
        return c

    summary = [
        card(grand.get("total_employees", 0), "Total Employees", "Int",      "blue"),
        card(flt(grand.get("amount")),         "Total Amount",    "Currency", "blue",   currency),
    ]

    if flt(grand.get("ot_amount")):
        summary.append(card(flt(grand.get("ot_amount")), "OT Amount", "Currency", "orange", currency))

    summary.append(card(flt(grand.get("gross_salary")), "Gross Salary", "Currency", "green", currency))

    if flt(grand.get("allowance")):
        summary.append(card(flt(grand.get("allowance")), "Allowance", "Currency", "blue", currency))
    if flt(grand.get("eobi")):
        summary.append(card(flt(grand.get("eobi")), "EOBI", "Currency", "purple", currency))
    if flt(grand.get("income_tax")):
        summary.append(card(flt(grand.get("income_tax")), "Income Tax", "Currency", "red", currency))

    summary.append(card(flt(grand.get("net_salary")), "Net Payable", "Currency", "green", currency))

    return summary