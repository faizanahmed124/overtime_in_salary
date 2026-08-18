import re
import json
import frappe
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        filters = {}
    # Force cash mode
    filters["mode_of_payment"] = "Cash"

    records, earn_comps, ded_comps = get_data(filters)
    columns = get_columns(records, earn_comps, ded_comps)
    summary = get_report_summary(records)
    return columns, records, None, None, summary


# ─────────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────────
def _fn(prefix, name):
    return (prefix + re.sub(r"[^a-z0-9]", "_", name.lower().strip()))[:52]


def _conditions(filters):
    c = "ss.docstatus = 1 AND ss.mode_of_payment = %(mode_of_payment)s"
    if filters.get("company"):
        c += " AND ss.company = %(company)s"
    if filters.get("from_date"):
        c += " AND ss.start_date >= %(from_date)s"
    if filters.get("to_date"):
        c += " AND ss.end_date <= %(to_date)s"
    if filters.get("employment_type"):
        c += " AND e.employment_type = %(employment_type)s"
    return c


# ─────────────────────────────────────────────────────────────────
# COLUMNS
# ─────────────────────────────────────────────────────────────────
def get_columns(records, earn_comps, ded_comps):
    check = [r for r in records if not r.get("_is_total")]

    def has(fn):
        return any(flt(r.get(fn)) for r in check)

    cols = [
        {"label": "Emp #",        "fieldname": "employee",      "fieldtype": "Link",
         "options": "Employee",   "width": 90},
        {"label": "Employee Name","fieldname": "employee_name", "fieldtype": "Data",  "width": 180},
        {"label": "Department",   "fieldname": "department",    "fieldtype": "Data",  "width": 150},
    ]

    for comp in earn_comps:
        fn = _fn("e_", comp)
        if has(fn):
            cols.append({"label": comp, "fieldname": fn, "fieldtype": "Currency", "width": 130, "precision": 0})

    if has("ot_amount"):
        cols.append({"label": "OT Amount", "fieldname": "ot_amount",
                     "fieldtype": "Currency", "width": 120, "precision": 0})

    cols.append({"label": "Gross",      "fieldname": "gross_salary",
                 "fieldtype": "Currency", "width": 140, "precision": 0})

    for comp in ded_comps:
        fn = _fn("d_", comp)
        if has(fn):
            cols.append({"label": comp, "fieldname": fn, "fieldtype": "Currency", "width": 120, "precision": 0})

    cols.append({"label": "Paid Salary", "fieldname": "net_salary",
                 "fieldtype": "Currency", "width": 140, "precision": 0})

    return cols


# ─────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────
def get_data(filters):
    cond = _conditions(filters)

    slips = frappe.db.sql(
        f"""
        SELECT
            ss.employee,
            MAX(ss.employee_name)                              AS employee_name,
            MAX(IFNULL(td.department_name, e.department, '—')) AS department,
            SUM(IFNULL(ss.custom_overtime_amount, 0))          AS ot_amount,
            SUM(IFNULL(ss.gross_pay, 0))                       AS gross_salary,
            SUM(IFNULL(ss.total_deduction, 0))                 AS total_deductions,
            SUM(IFNULL(NULLIF(ss.rounded_total,0), ss.net_pay)) AS net_salary,
            GROUP_CONCAT(ss.name)                              AS salary_slip
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e  ON e.name  = ss.employee
        LEFT JOIN `tabDepartment` td ON td.name = e.department
        WHERE {cond}
        GROUP BY ss.employee
        ORDER BY CAST(ss.employee AS UNSIGNED) ASC,
                 ss.employee ASC
        """,
        filters,
        as_dict=True,
    )

    if not slips:
        return [], [], []

    # Flatten all slip names from GROUP_CONCAT
    slip_names = []
    for r in slips:
        slip_names.extend((r.salary_slip or "").split(","))

    # ── All components in one query ───────────────────────────────
    comp_rows = frappe.db.sql(
        """
        SELECT parent, salary_component, parentfield, SUM(amount) AS amount
        FROM   `tabSalary Detail`
        WHERE  parent      IN %(slips)s
          AND  amount       > 0
        GROUP  BY parent, salary_component, parentfield
        ORDER  BY parentfield DESC, salary_component ASC
        """,
        {"slips": slip_names},
        as_dict=True,
    )

    # Unique ordered component lists
    earn_comps, ded_comps = [], []
    seen_e, seen_d = set(), set()
    for c in comp_rows:
        if c.parentfield == "earnings" and c.salary_component not in seen_e:
            earn_comps.append(c.salary_component); seen_e.add(c.salary_component)
        elif c.parentfield == "deductions" and c.salary_component not in seen_d:
            ded_comps.append(c.salary_component); seen_d.add(c.salary_component)

    # slip → {(component, parentfield): amount}
    slip_comp = {}
    for c in comp_rows:
        slip_comp.setdefault(c.parent, {})[(c.salary_component, c.parentfield)] = flt(c.amount)

    # Enrich records — salary_slip is now GROUP_CONCAT (comma-separated)
    for r in slips:
        emp_slips = (r.salary_slip or "").split(",")   # all slips for this employee
        earn_dict, ded_dict = {}, {}

        for comp in earn_comps:
            fn  = _fn("e_", comp)
            val = sum(flt(slip_comp.get(sn, {}).get((comp, "earnings"), 0))
                      for sn in emp_slips)
            r[fn] = val
            if val:
                earn_dict[comp] = val

        if flt(r.ot_amount):
            earn_dict["OT Amount"] = flt(r.ot_amount)

        for comp in ded_comps:
            fn  = _fn("d_", comp)
            val = sum(flt(slip_comp.get(sn, {}).get((comp, "deductions"), 0))
                      for sn in emp_slips)
            r[fn] = val
            if val:
                ded_dict[comp] = val

        # Hidden JSON for print slips
        r["_earn"] = json.dumps(earn_dict)
        r["_ded"]  = json.dumps(ded_dict)

    # Grand Total
    grand = {
        "employee":      "",
        "employee_name": "<b>Grand Total</b>",
        "department":    "",
        "ot_amount":     sum(flt(r.ot_amount)        for r in slips),
        "gross_salary":  sum(flt(r.gross_salary)     for r in slips),
        "total_deductions": sum(flt(r.total_deductions) for r in slips),
        "net_salary":    sum(flt(r.net_salary)       for r in slips),  # rounded_total
        "_is_total":     True,
    }
    for comp in earn_comps:
        fn = _fn("e_", comp)
        grand[fn] = sum(flt(r.get(fn)) for r in slips)
    for comp in ded_comps:
        fn = _fn("d_", comp)
        grand[fn] = sum(flt(r.get(fn)) for r in slips)

    slips.append(grand)
    return slips, earn_comps, ded_comps


# ─────────────────────────────────────────────────────────────────
# SUMMARY  (KPI cards)
# ─────────────────────────────────────────────────────────────────
def get_report_summary(data):
    grand = next((r for r in data if r.get("_is_total")), None)
    if not grand:
        return None

    emp_count = sum(1 for r in data if r.get("employee") and not r.get("_is_total"))
    currency  = frappe.defaults.get_global_default("currency") or "PKR"

    def card(v, label, dtype, ind, curr=None):
        c = {"value": v, "label": label, "datatype": dtype, "indicator": ind}
        if curr: c["currency"] = curr
        return c

    cards = [card(emp_count, "Cash Employees", "Int", "blue")]
    base  = flt(grand.get("gross_salary")) - flt(grand.get("ot_amount"))
    if base:
        cards.append(card(base, "Total Amount", "Currency", "blue", currency))
    if flt(grand.get("ot_amount")):
        cards.append(card(flt(grand.get("ot_amount")), "OT Amount", "Currency", "orange", currency))
    cards.append(card(flt(grand.get("gross_salary")),     "Gross Salary",     "Currency", "green", currency))
    cards.append(card(flt(grand.get("total_deductions")), "Total Deductions", "Currency", "red",   currency))
    cards.append(card(flt(grand.get("net_salary")),       "Paid Salary",      "Currency", "green", currency))
    return cards