frappe.ui.form.on("Citizenship Enrollment", {
    status(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.status === "completed" && !row.videos_completed) {
            frappe.show_alert({ message: __("Mark videos completed before setting status to Completed"), indicator: "orange" });
        }
    },
});