frappe.ui.form.on("Program", {

    refresh(frm) {
        frm.trigger("set_field_descriptions");
        frm.trigger("add_custom_buttons");
        frm.trigger("highlight_status");
    },

    set_field_descriptions(frm) {
        frm.set_df_property(
            "reg_end_date",
            "description",
            "Must be on or before the program start date."
        );
        frm.set_df_property(
            "batch_id",
            "description",
            "Unique identifier for this batch. Cannot be changed after creation."
        );
    },

    add_custom_buttons(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("View Active Programs"),
                () => {
                    frappe.set_route("List", "Program", {
                        start: ["<=", frappe.datetime.get_today()],
                        end: [">=", frappe.datetime.get_today()],
                    });
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
                                frappe.msgprint({
                                    title: __("Program Summary"),
                                    message: `
                                        <table class="table table-bordered">
                                            <tr><td><b>Program</b></td><td>${d.program || "-"}</td></tr>
                                            <tr><td><b>Batch ID</b></td><td>${d.batch_id || "-"}</td></tr>
                                            <tr><td><b>Batch</b></td><td>${d.batch || "-"}</td></tr>
                                            <tr><td><b>Course Level</b></td><td>${d.course_level || "-"}</td></tr>
                                            <tr><td><b>Start</b></td><td>${d.start || "-"}</td></tr>
                                            <tr><td><b>End</b></td><td>${d.end || "-"}</td></tr>
                                            <tr><td><b>Reg End Date</b></td><td>${d.reg_end_date || "-"}</td></tr>
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

    highlight_status(frm) {
        if (frm.is_new()) return;

        const today = frappe.datetime.get_today();
        const start = frm.doc.start;
        const end = frm.doc.end;

        if (start && end) {
            if (today >= start && today <= end) {
                frm.dashboard.set_headline_alert(
                    __("This program is currently active."),
                    "green"
                );
            } else if (today < start) {
                frm.dashboard.set_headline_alert(
                    __("This program has not started yet."),
                    "blue"
                );
            } else {
                frm.dashboard.set_headline_alert(
                    __("This program has ended."),
                    "orange"
                );
            }
        }
    },

    start(frm) {
        frm.trigger("validate_date_order");
    },

    end(frm) {
        frm.trigger("validate_date_order");
    },

    reg_end_date(frm) {
        if (frm.doc.reg_end_date && frm.doc.start) {
            if (frm.doc.reg_end_date > frm.doc.start) {
                frappe.msgprint({
                    message: __("Registration End Date should be on or before the Start date."),
                    indicator: "orange",
                });
                frm.set_value("reg_end_date", "");
            }
        }
    },

    validate_date_order(frm) {
        if (frm.doc.start && frm.doc.end) {
            if (frm.doc.start >= frm.doc.end) {
                frappe.msgprint({
                    message: __("End date must be after Start date."),
                    indicator: "red",
                });
                frm.set_value("end", "");
            }
        }
    },
});