import frappe


def update_single_employee_assignments(doc, method):
    """
    Triggered automatically when an Employee is saved (on_update).
    Updates the 'base' field for ALL related Salary Structure Assignments
    (draft or submitted) belonging to this employee.
    """
    new_base = None
    if doc.employment_type == "PERMANENT":
        new_base = doc.ctc
    elif doc.employment_type == "DAILY WAGES":
        new_base = doc.custom_basic_pay

    if new_base is None:
        return

    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": doc.name, "docstatus": ["!=", 2]},
        pluck="name",
    )

    for name in assignments:
        frappe.db.set_value(
            "Salary Structure Assignment", name, "base", new_base, update_modified=False
        )

    if assignments:
        frappe.db.commit()


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
