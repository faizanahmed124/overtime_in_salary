import frappe
from frappe.utils import flt


def get_base_for_employee(employment_type, ctc, custom_basic_pay):
    """PERMANENT -> CTC, DAILY WAGES -> Basic Pay. None when the type has no mapping."""
    if employment_type == "PERMANENT":
        return ctc
    if employment_type == "DAILY WAGES":
        return custom_basic_pay
    return None


def update_single_employee_assignments(doc, method=None):
    """
    Pushes the employee's CTC / Basic Pay into 'base' on ALL of the employee's
    Salary Structure Assignments (draft or submitted, not cancelled).
    Runs inside the Employee save transaction (no commit here); returns True
    when at least one assignment changed.
    """
    new_base = get_base_for_employee(doc.employment_type, doc.ctc, doc.custom_basic_pay)

    # an empty/zero amount must never wipe the base used by payroll
    if not flt(new_base):
        return False

    changed = False
    for a in frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": doc.name, "docstatus": ["!=", 2]},
        fields=["name", "base"],
    ):
        if flt(a.base) != flt(new_base):
            frappe.db.set_value(
                "Salary Structure Assignment", a.name, "base", flt(new_base), update_modified=False
            )
            changed = True

    return changed


@frappe.whitelist()
def update_all_salary_structure_assignments():
    """
    Bulk update: loops through ALL Salary Structure Assignment records
    (draft or submitted, skips cancelled) and refreshes 'base' from the
    linked Employee's employment_type (PERMANENT -> ctc, DAILY WAGES -> custom_basic_pay).
    Called from the 'Update Base Salary' button on the list view.
    """
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": ["!=", 2]},
        fields=["name", "employee"],
    )

    updated_count = 0
    skipped_count = 0
    errors = []

    for a in assignments:
        if not a.employee:
            skipped_count += 1
            continue

        emp = frappe.db.get_value(
            "Employee",
            a.employee,
            ["employment_type", "ctc", "custom_basic_pay"],
            as_dict=True,
        )

        if not emp:
            skipped_count += 1
            continue

        new_base = None
        if emp.employment_type == "PERMANENT":
            new_base = emp.ctc
        elif emp.employment_type == "DAILY WAGES":
            new_base = emp.custom_basic_pay

        if new_base is None:
            skipped_count += 1
            continue

        try:
            frappe.db.set_value(
                "Salary Structure Assignment", a.name, "base", new_base, update_modified=False
            )
            updated_count += 1
        except Exception as e:
            errors.append(f"{a.name}: {str(e)}")

    frappe.db.commit()

    return {"updated": updated_count, "skipped": skipped_count, "errors": errors}
