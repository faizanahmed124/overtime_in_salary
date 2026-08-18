frappe.ui.form.on('Salary Slip', {
    onload(frm) {
        // Purana listener hatao taake duplicate na bane (form dubara load hone par)
        frappe.realtime.off('salary_slip_auto_updated');

        frappe.realtime.on('salary_slip_auto_updated', (data) => {
            // Sirf isi khuli hui slip ke liye reload karo, aur sirf draft ho
            if (data.salary_slip === frm.doc.name && frm.doc.docstatus === 0) {
                frm.reload_doc();
                frappe.show_alert({
                    message: __("Live data updated"),
                    indicator: "green"
                });
            }
        });
    }
});

