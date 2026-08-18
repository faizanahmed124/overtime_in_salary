frappe.listview_settings["Salary Structure Assignment"] = {
    onload: function (listview) {
        listview.page.add_inner_button(__("Update Base Salary"), function () {
            frappe.confirm(
                __("This will update the Base field for ALL Salary Structure Assignments (draft and submitted) based on each Employee's current CTC / Basic Pay. Continue?"),
                function () {
                    frappe.call({
                        method: "overtime_in_salary.overtime_in_salary.base_update.update_all_salary_structure_assignments",
                        freeze: true,
                        freeze_message: __("Updating Base Salaries..."),
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __("Update Complete"),
                                    message: __(
                                        "Updated: {0}<br>Skipped: {1}<br>Errors: {2}",
                                        [
                                            r.message.updated,
                                            r.message.skipped,
                                            r.message.errors.length,
                                        ]
                                    ),
                                    indicator: "green",
                                });
                                listview.refresh();
                            }
                        },
                    });
                }
            );
        });
    },
};
