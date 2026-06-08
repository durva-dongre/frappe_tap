frappe.ui.form.on("Citizenship Auth Profile", {
    citizenship_learner(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.citizenship_learner) {
            row.student_name = "";
            frm.refresh_field("students");
        }
    }
});