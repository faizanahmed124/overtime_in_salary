import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    report_summary = get_report_summary(data)
    return columns, data, None, chart, report_summary


# ──────────────────────────────────────────────
# COLUMNS
# ──────────────────────────────────────────────
def get_columns():
    return [
        {
            "label": "Employee ID",
            "fieldname": "employee_id",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 200,
        },
        {
            "label": "Total Gratuity",
            "fieldname": "total_gratuity",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": "Consumed Gratuity",
            "fieldname": "consumed_gratuity",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": "Remaining Gratuity",
            "fieldname": "remaining_gratuity",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": "Consumed %",
            "fieldname": "consumed_percentage",
            "fieldtype": "Percent",
            "width": 150,
        },
    ]


# ──────────────────────────────────────────────
# DATA
# ──────────────────────────────────────────────
def get_data(filters):
    conditions = "e.status = 'Active' AND IFNULL(e.custom_total_gratuity, 0) > 0"

    if filters.get("department"):
        conditions += " AND e.department = %(department)s"

    if filters.get("company"):
        conditions += " AND e.company = %(company)s"

    records = frappe.db.sql(f"""
        SELECT
            e.attendance_device_id                                      AS employee_id,
            e.employee_name                                             AS employee_name,
            e.department                                                AS department,
            ROUND(IFNULL(e.custom_total_gratuity, 0))                   AS total_gratuity,
            ROUND(IFNULL(e.custom_consumed_gratuity_amount, 0))         AS consumed_gratuity,
            ROUND(
                IFNULL(e.custom_total_gratuity, 0)
                - IFNULL(e.custom_consumed_gratuity_amount, 0)
            )                                                           AS remaining_gratuity,
            ROUND(
                (
                    IFNULL(e.custom_consumed_gratuity_amount, 0)
                    / NULLIF(e.custom_total_gratuity, 0)
                ) * 100
            )                                                           AS consumed_percentage
        FROM `tabEmployee` e
        WHERE {conditions}
        ORDER BY e.department ASC, e.employee_name ASC
    """, filters, as_dict=True)

    # Grand Total row
    if records:
        grand_total = {
            "employee_id":         "",
            "employee_name":       "<b>Grand Total</b>",
            "department":          "",
            "total_gratuity":      sum(flt(r.total_gratuity)    for r in records),
            "consumed_gratuity":   sum(flt(r.consumed_gratuity) for r in records),
            "remaining_gratuity":  sum(flt(r.remaining_gratuity) for r in records),
            "consumed_percentage": round(
                sum(flt(r.consumed_gratuity) for r in records)
                / (sum(flt(r.total_gratuity) for r in records) or 1)
                * 100
            ),
        }
        records.append(grand_total)

    return records


# ──────────────────────────────────────────────
# CHART — Department-wise Gratuity Bar Chart
# ──────────────────────────────────────────────
def get_chart(data):
    if not data:
        return None

    # Group by department (skip Grand Total row)
    rows = [r for r in data if r.get("employee_name") != "<b>Grand Total</b>"]

    dept_map = {}
    for r in rows:
        dept = r.get("department") or "—"
        if dept not in dept_map:
            dept_map[dept] = {"total": 0, "consumed": 0, "remaining": 0}
        dept_map[dept]["total"]     += flt(r.get("total_gratuity"))
        dept_map[dept]["consumed"]  += flt(r.get("consumed_gratuity"))
        dept_map[dept]["remaining"] += flt(r.get("remaining_gratuity"))

    labels    = list(dept_map.keys())
    total     = [dept_map[d]["total"]     for d in labels]
    consumed  = [dept_map[d]["consumed"]  for d in labels]
    remaining = [dept_map[d]["remaining"] for d in labels]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Total Gratuity",     "values": total},
                {"name": "Consumed Gratuity",  "values": consumed},
                {"name": "Remaining Gratuity", "values": remaining},
            ],
        },
        "type": "bar",
        "colors": ["#5E81F4", "#F45E7A", "#5EF4A2"],
        "barOptions": {
            "stacked": False,
            "spaceRatio": 0.3,
        },
        "height": 280,
    }


# ──────────────────────────────────────────────
# REPORT SUMMARY — KPI Cards at top
# ──────────────────────────────────────────────
def get_report_summary(data):
    if not data:
        return None

    rows = [r for r in data if r.get("employee_name") != "<b>Grand Total</b>"]

    total_employees  = len(rows)
    total_gratuity   = sum(flt(r.get("total_gratuity"))    for r in rows)
    consumed_gratuity = sum(flt(r.get("consumed_gratuity")) for r in rows)
    remaining_gratuity = sum(flt(r.get("remaining_gratuity")) for r in rows)
    consumed_pct = round((consumed_gratuity / (total_gratuity or 1)) * 100)

    return [
        {
            "value": total_employees,
            "label": "Total Employees",
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "value": total_gratuity,
            "label": "Total Gratuity",
            "datatype": "Currency",
            "indicator": "blue",
        },
        {
            "value": consumed_gratuity,
            "label": "Consumed Gratuity",
            "datatype": "Currency",
            "indicator": "orange",
        },
        {
            "value": remaining_gratuity,
            "label": "Remaining Gratuity",
            "datatype": "Currency",
            "indicator": "green",
        },
        {
            "value": consumed_pct,
            "label": "Consumed %",
            "datatype": "Percent",
            "indicator": "red" if consumed_pct > 75 else "orange" if consumed_pct > 50 else "green",
        },
    ]