frappe.ui.form.on("Tap Voice Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Check Setup"), () => {
			frappe.call({
				method: "tap_lms.tapvoice.api.operator.check_setup",
				callback: (r) => {
					if (!r.message) {
						return;
					}
					const rows = Object.entries(r.message)
						.filter(([key]) => key !== "all_ok")
						.map(([key, value]) => {
							const ok = value && value.ok;
							const icon = ok ? "✅" : "❌";
							const detail = value && (value.missing || value.error || value.value || value.max_len || "");
							return `<tr><td>${icon} ${key}</td><td>${detail || ""}</td></tr>`;
						})
						.join("");
					const html = `<table class="table table-bordered"><tbody>${rows}</tbody></table>`;
					frappe.msgprint({
						title: r.message.all_ok ? __("Setup OK") : __("Setup Issues Found"),
						message: html,
						indicator: r.message.all_ok ? "green" : "red",
					});
				},
			});
		});
	},
});