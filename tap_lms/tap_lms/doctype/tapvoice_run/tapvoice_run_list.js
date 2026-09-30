frappe.listview_settings["Tap Voice Run"] = {
	add_fields: ["status", "written", "estimated_cost_usd_final", "creation"],

	get_indicator(doc) {
		const green = ["Completed"];
		const active = ["Deploying", "Starting", "Running", "Stopping"];
		const grey = ["Skipped", "Draft"];
		const red = ["Failed", "Lost", "Timed Out", "Deploy Failed"];

		if (green.includes(doc.status)) {
			return [__(doc.status), "green", "status,=," + doc.status];
		}
		if (active.includes(doc.status)) {
			return [__(doc.status), "orange", "status,=," + doc.status];
		}
		if (grey.includes(doc.status)) {
			return [__(doc.status), "grey", "status,=," + doc.status];
		}
		if (red.includes(doc.status)) {
			return [__(doc.status), "red", "status,=," + doc.status];
		}
		if (doc.status === "Completed With Failures") {
			return [__(doc.status), "yellow", "status,=," + doc.status];
		}
		return [__(doc.status), "grey", "status,=," + doc.status];
	},

	onload(listview) {
		listview.page.add_menu_item(__("Start New Batch"), () => {
			frappe.confirm(__("Start a new TapVoice batch now?"), () => {
				frappe.call({
					method: "tap_lms.tapvoice.api.operator.start_batch_manual",
					callback: () => {
						frappe.show_alert({ message: __("Batch queued"), indicator: "green" });
						listview.refresh();
					},
				});
			});
		});

		listview.page.add_menu_item(__("Create Draft"), () => {
			frappe.call({
				method: "tap_lms.tapvoice.api.operator.create_draft",
				callback: (r) => {
					if (r.message && r.message.name) {
						frappe.set_route("Form", "Tap Voice Run", r.message.name);
					}
				},
			});
		});

		listview.page.add_menu_item(__("Preview Eligible"), () => {
			frappe.call({
				method: "tap_lms.tapvoice.api.operator.preview_eligible",
				callback: (r) => {
					if (!r.message) {
						return;
					}
					const m = r.message;
					const rows = Object.entries(m)
						.map(([key, value]) => `<tr><td>${key}</td><td>${JSON.stringify(value)}</td></tr>`)
						.join("");
					frappe.msgprint({
						title: __("Preview: {0}", [m.decision]),
						message: `<table class="table table-bordered"><tbody>${rows}</tbody></table>`,
						indicator: m.decision === "Deploy" ? "green" : "orange",
					});
				},
			});
		});
	},
};