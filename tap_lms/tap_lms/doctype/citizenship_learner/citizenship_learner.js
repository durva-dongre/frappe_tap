frappe.ui.form.on("Citizenship Learner", {
    refresh(frm) {
        frm.set_df_property("longest_streak", "read_only", 1);

        if (!frm.is_new()) {
            frm.add_custom_button(__("Record Activity"), () => {
                _show_activity_dialog(frm);
            });
        }
    },
});

function _show_activity_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Record Activity"),
        fields: [
            { label: "Course", fieldname: "course", fieldtype: "Link", options: "Course Level", reqd: 1 },
            { label: "XP to Award", fieldname: "xp", fieldtype: "Int", reqd: 1 },
            { label: "Video Index (leave blank for quiz/other)", fieldname: "video_index", fieldtype: "Int" },
        ],
        primary_action_label: __("Submit"),
        primary_action(values) {
            frappe.call({
                method: "tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner.record_activity",
                args: {
                    student: frm.doc.student,
                    course: values.course,
                    xp: values.xp,
                    video_index: values.video_index || null,
                },
                callback(r) {
                    if (!r.exc) {
                        frappe.show_alert({
                            message: __("Activity recorded — XP: {0}, Streak: {1}", [r.message.xp, r.message.streak]),
                            indicator: "green",
                        });
                        frm.reload_doc();
                    }
                },
            });
            d.hide();
        },
    });
    d.show();
}