import frappe
from .progress import update_content_progress, get_course_progress


@frappe.whitelist(allow_guest=True)
def update_quiz_progress(student_id=None, course=None, quiz_index=None, xp=None, lang=None, fetch_next=None):
    fd = frappe.form_dict
    return update_content_progress(
        student_id=student_id or fd.get("student_id"),
        course=course or fd.get("course"),
        quiz_index=quiz_index if quiz_index is not None else fd.get("quiz_index"),
        xp=xp if xp is not None else fd.get("xp"),
        lang=lang or fd.get("lang"),
        fetch_next=fetch_next if fetch_next is not None else fd.get("fetch_next"),
    )


@frappe.whitelist(allow_guest=True)
def get_quiz_progress(student_id=None, course=None, lang=None):
    fd = frappe.form_dict
    return get_course_progress(
        student_id=student_id or fd.get("student_id"),
        course=course or fd.get("course"),
        lang=lang or fd.get("lang"),
        fields="xp,course_meta",
    )