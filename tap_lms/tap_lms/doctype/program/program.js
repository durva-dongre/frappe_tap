frappe.ui.form.on("Program", {

    refresh(frm) {
        frm.trigger("set_field_descriptions");
        frm.trigger("add_custom_buttons");
        frm.trigger("render_batches_dashboard");
    },

    set_field_descriptions(frm) {
        frm.set_df_property(
            "course_level",
            "description",
            "The course level associated with this program."
        );
    },

    add_custom_buttons(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Create Batch"),
                () => {
                    frappe.new_doc("Batch", { program: frm.doc.name });
                },
                __("Actions")
            );

            frm.add_custom_button(
                __("View Batches"),
                () => {
                    frappe.set_route("List", "Batch", { program: frm.doc.name });
                },
                __("Actions")
            );

            frm.add_custom_button(
                __("Program Summary"),
                () => {
                    frappe.call({
                        method: "tap_lms.tap_lms.doctype.program.program.get_program_summary",
                        args: { program_name: frm.doc.name },
                        callback(r) {
                            if (r.message) {
                                const d = r.message;
                                const batch_rows = d.batches.map(b => `
                                    <tr>
                                        <td>${b.name1 || "-"}</td>
                                        <td>${b.batch_id || "-"}</td>
                                        <td>${b.start_date || "-"}</td>
                                        <td>${b.end_date || "-"}</td>
                                        <td>${b.active ? "Yes" : "No"}</td>
                                    </tr>
                                `).join("");

                                frappe.msgprint({
                                    title: __("Program Summary"),
                                    message: `
                                        <p><b>Program:</b> ${d.program || "-"}</p>
                                        <p><b>Course Level:</b> ${d.course_level || "-"}</p>
                                        <p><b>Total Batches:</b> ${d.total_batches}</p>
                                        <p><b>Active Batches:</b> ${d.active_batches}</p>
                                        <table class="table table-bordered" style="margin-top:10px;">
                                            <thead>
                                                <tr>
                                                    <th>Name</th>
                                                    <th>Batch ID</th>
                                                    <th>Start</th>
                                                    <th>End</th>
                                                    <th>Active</th>
                                                </tr>
                                            </thead>
                                            <tbody>${batch_rows || "<tr><td colspan='5'>No batches found.</td></tr>"}</tbody>
                                        </table>
                                    `,
                                    indicator: "blue",
                                });
                            }
                        },
                    });
                },
                __("Actions")
            );
        }
    },

    render_batches_dashboard(frm) {
        if (frm.is_new()) return;

        frappe.call({
            method: "tap_lms.tap_lms.doctype.program.program.get_batches",
            args: { program_name: frm.doc.name },
            callback(r) {
                if (r.message) {
                    const total = r.message.length;
                    const active = r.message.filter(b => b.active).length;
                    frm.dashboard.set_headline_alert(
                        __("{0} batch(es) — {1} active", [total, active]),
                        active > 0 ? "green" : "orange"
                    );
                }
            },
        });
    },
});