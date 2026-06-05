frappe.ui.form.on("LearningUnitTranslation", {
    language(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.language) return;
        if (row.translated_name) return;
        const parent_doc = frm.doc;
        if (parent_doc && parent_doc.unit_name) {
            frappe.model.set_value(cdt, cdn, "translated_name", parent_doc.unit_name);
        }
    },
});