frappe.ui.form.on("Citizenship Tasks", {
    refresh(frm) {
        frm.fields_dict.retrigger.$input.off("click").on("click", () => {
            frappe.call({
                method: "retrigger",
                doc: frm.doc,
                callback: () => {
                    frappe.show_alert({ message: "Job queued", indicator: "blue" });
                    frm.reload_doc();
                }
            });
        });
    }
});