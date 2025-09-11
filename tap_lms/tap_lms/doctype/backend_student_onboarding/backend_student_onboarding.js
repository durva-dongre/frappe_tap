// Copyright (c) 2025, Techt4dev and contributors
// For license information, please see license.txt

frappe.ui.form.on('Backend Student Onboarding', {
	// refresh: function(frm) {

	// }
	validate: function(frm) {
		console.log("Validating and updating student count...");
		update_student_count(frm)
	}
});

function update_student_count(frm) {
    let count = 0;
    if (frm.doc.students) {
        frm.doc.students.forEach(row => {
            if (row.processing_status === "Pending") {
                count++;
            }
        });
    }
    frm.set_value("student_count", count);
}
