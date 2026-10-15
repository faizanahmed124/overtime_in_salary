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
    },

    after_save(frm) {
        // our own save should not trigger another tally right away
        frm.__last_tally = Date.now();
    },

    refresh(frm) {
        // Tally the draft slip every time it is opened (also when reopened from the browser cache)
        if (frm.is_new() || frm.doc.docstatus !== 0 || frm.is_dirty()) return;
        if (frm.__tallying) return;
        // the refresh fired by our own reload/save comes within a few seconds; a real re-open does not
        if (frm.__last_tally && Date.now() - frm.__last_tally < 4000) return;
        frm.__tallying = true;

        frappe.dom.freeze(__("Loading data..."));
        frappe.call({
            method: "overtime_in_salary.overtime_in_salary.utils.draft_slip_refresh.refresh_draft_slip",
            args: { name: frm.doc.name },
        }).then((r) => {
            // reload when the server changed the slip OR our cached copy is older than the server's
            const stale = r.message && r.message.modified && String(r.message.modified) !== String(frm.doc.modified);
            if (r.message && (r.message.updated || stale)) {
                frm.__last_tally = Date.now();   // the reload below fires refresh again
                return frm.reload_doc().then(() =>
                    frappe.show_alert({ message: __("Salary Slip updated with latest data"), indicator: "green" })
                );
            }
        }).always(() => {
            frm.__last_tally = Date.now();
            frm.__tallying = false;
            frappe.dom.unfreeze();
        });
    }
});
