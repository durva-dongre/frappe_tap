frappe.ui.form.on("Student Auth", {
    refresh(frm) {
        frm.set_query("student", "students", function () {
            return {
                filters: {
                    status: "active"
                }
            };
        });
    },

    phone(frm) {
        if (frm.doc.phone) {
            frm.set_value("phone", frm.doc.phone.replace(/\s+/g, ""));
        }
    },

    is_locked(frm) {
        if (!frm.doc.is_locked) {
            frm.set_value("failed_attempts", 0);
            frm.set_value("locked_until", null);
        }
    }
});