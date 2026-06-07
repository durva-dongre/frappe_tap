frappe.ui.form.on("Student Auth Profile", {
    student(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.student) {
            row.student_name = "";
            frm.refresh_field("students");
        }
    }
});