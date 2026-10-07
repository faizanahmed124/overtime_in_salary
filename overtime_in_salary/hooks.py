app_name = "overtime_in_salary"
app_title = "Overtime In Salary"
app_publisher = "Faizan"
app_description = "Show overtime in salary"
app_email = "Faizanahmed1295@gmail.com"
app_license = "mit"


doc_events = {
    "Salary Slip": {
        "validate": "overtime_in_salary.overtime_in_salary.salary_slip.calculate_overtime"
    },
    "Attendance": {
        "on_submit": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_attendance_change",
        "on_cancel": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_attendance_change",
        "on_update_after_submit": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_attendance_change",
    },
    "Additional Salary": {
        "on_submit": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_additional_salary_change",
        "on_cancel": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_additional_salary_change",
    },
    "Employee": {
        "on_update": "overtime_in_salary.overtime_in_salary.utils.salary_triggers.on_employee_change",
    },
}
override_doctype_class = {
    "Leave Type": "overtime_in_salary.overtime_in_salary.overrides.leave_type.CustomLeaveType"
}

doctype_js = {
    "Salary Slip": "public/js/salary_slip.js",
    "Employee": "public/js/employee.js",
}


# Apps
# ------------------