import frappe


@frappe.whitelist(allow_guest=True)
def get_quizzes(unit_id: str, language: str = None):
    filters = {"learning_unit": unit_id}
    if language:
        filters["language"] = language
    quizzes = frappe.get_all(
        "Learning Unit Quiz",
        filters=filters,
        fields=["name as id", "title", "language", "total_questions"],
        order_by="creation asc",
    )
    return {
        "unit_id": unit_id,
        "language": language,
        "quizzes": quizzes,
        "total": len(quizzes),
    }


@frappe.whitelist(allow_guest=True)
def get_quiz(quiz_id: str):
    doc = frappe.get_doc("Learning Unit Quiz", quiz_id)
    questions = []
    for q in (doc.questions or []):
        options = []
        for opt in (q.options or []):
            options.append({
                "id": opt.name,
                "text": opt.option_text if hasattr(opt, "option_text") else str(opt),
                "is_correct": opt.is_correct if hasattr(opt, "is_correct") else False,
            })
        questions.append({
            "id": q.name,
            "question": q.question if hasattr(q, "question") else str(q),
            "options": options,
        })
    return {
        "id": doc.name,
        "title": doc.title if hasattr(doc, "title") else None,
        "language": doc.language if hasattr(doc, "language") else None,
        "learning_unit": doc.learning_unit if hasattr(doc, "learning_unit") else None,
        "questions": questions,
        "total_questions": len(questions),
    }