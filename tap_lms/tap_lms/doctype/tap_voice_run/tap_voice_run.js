const TAPVOICE_ACTIVE_STATUSES = ["Deploying", "Starting", "Running", "Stopping"];

frappe.ui.form.on("Tap Voice Run", {
	refresh(frm) {
		frm.disable_save();

		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Deploy Pod"), () => {
				frappe.call({
					method: "tap_lms.tapvoice.api.operator.deploy_run",
					args: { run_name: frm.doc.name },
					callback: () => frm.reload_doc(),
				});
			});
		}

		frm.add_custom_button(__("Refresh Status"), () => {
			frappe.call({
				method: "tap_lms.tapvoice.api.operator.refresh_status",
				args: { run_name: frm.doc.name },
				callback: () => frm.reload_doc(),
			});
		});

		if (TAPVOICE_ACTIVE_STATUSES.includes(frm.doc.status)) {
			frm.add_custom_button(__("Cancel Run"), () => {
				frappe.confirm(__("Stop this run?"), () => {
					frappe.call({
						method: "tap_lms.tapvoice.api.operator.cancel_run",
						args: { run_name: frm.doc.name },
						callback: () => frm.reload_doc(),
					});
				});
			});
		}

		frm.add_custom_button(__("Force Terminate"), () => {
			frappe.confirm(
				__("This immediately deletes the RunPod pod, even if work is in progress. Continue?"),
				() => {
					frappe.call({
						method: "tap_lms.tapvoice.api.operator.force_terminate",
						args: { run_name: frm.doc.name },
						callback: () => frm.reload_doc(),
					});
				}
			);
		});

		if (frm.doc.termination_status && frm.doc.termination_status !== "Not Needed") {
			frm.add_custom_button(__("Verify Termination"), () => {
				frappe.call({
					method: "tap_lms.tapvoice.api.operator.verify_termination",
					args: { run_name: frm.doc.name },
					callback: () => frm.reload_doc(),
				});
			});
		}

		if (frm.doc.decision || frm.doc.status_reason) {
			frm.dashboard.set_headline(
				`${frm.doc.decision || ""} — ${frm.doc.status_reason || ""}`
			);
		}

		if (TAPVOICE_ACTIVE_STATUSES.includes(frm.doc.status)) {
			clearTimeout(frm._tapvoice_refresh_timer);
			frm._tapvoice_refresh_timer = setTimeout(() => {
				if (!frm.is_dirty()) {
					frm.reload_doc();
				}
			}, 15000);
		}
	},
});