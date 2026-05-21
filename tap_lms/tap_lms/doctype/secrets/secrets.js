frappe.ui.form.on("Secrets", {
    refresh(frm) {
        frm.set_intro("System secrets are encrypted and restricted.");
    }
});