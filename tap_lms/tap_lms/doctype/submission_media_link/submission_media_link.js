frappe.ui.form.on("Submission Media Link", {
	url(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.url && !row.url.startsWith("http://") && !row.url.startsWith("https://")) {
			frappe.model.set_value(cdt, cdn, "url", "");
			frappe.msgprint(__("URL must start with http:// or https://"));
		}
	},

	media_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.media_type) return;

		const placeholders = {
			Drive: "https://drive.google.com/...",
			YouTube: "https://www.youtube.com/...",
			Plio: "https://app.plio.in/...",
			Canva: "https://www.canva.com/...",
		};

		if (placeholders[row.media_type] && !row.url) {
			frappe.model.set_value(cdt, cdn, "url", "");
		}
	},
});