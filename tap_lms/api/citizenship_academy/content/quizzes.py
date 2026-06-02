import frappe

@frappe.whitelist(allow_guest=True)
def get_quizzes_for_unit(unit_id: str, language: str = None):
    unit = frappe.get_doc("LearningUnit", unit_id)
    quiz_ids = [
        row.content for row in (unit.content_items or [])
        if (row.content_type or "").lower() == "quiz" and row.content
    ]
    if not quiz_ids:
        return {"unit_id": unit_id, "quizzes": [], "total": 0}

    quizzes = []
    for qid in quiz_ids:
        try:
            doc = frappe.get_doc("Quiz", qid)
            quizzes.append({
                "id":              doc.name,
                "title":           getattr(doc, "quiz_name", None),
                "passing_score":   getattr(doc, "passing_score", 60),
                "total_questions": getattr(doc, "total_questions", 0),
            })
        except Exception:
            continue

    return {"unit_id": unit_id, "quizzes": quizzes, "total": len(quizzes)}


@frappe.whitelist(allow_guest=True)
def get_quiz(quiz_id: str):
    doc = frappe.get_doc("Quiz", quiz_id)

    labels = "ABCDEFGHIJ"
    questions = []

    for q_row in (doc.questions or []):
        # q_row is QuizQuestionList — has 'question' link to QuizQuestion
        try:
            q = frappe.get_doc("QuizQuestion", q_row.question)
        except Exception:
            continue

        # Build lettered options by fetching each QuizOption
        options = {}
        correct_letter = ""
        correct_idx = (getattr(q, "correct_option", 0) or 0)

        for idx, opt_row in enumerate(q.options or []):
            try:
                opt = frappe.get_doc("QuizOption", opt_row.options)
                letter = labels[idx] if idx < len(labels) else str(idx)
                options[letter] = getattr(opt, "option_text", "") or ""
                if (idx + 1) == correct_idx:
                    correct_letter = letter
            except Exception:
                continue

        questions.append({
            "id":             q.name,
            "text":           getattr(q, "question", "") or "",
            "options":        options,
            "correct_option": correct_letter,
            "explanation":    getattr(q, "explanation", None),
        })

    return {
        "id":              doc.name,
        "title":           getattr(doc, "quiz_name", None),
        "passing_score":   getattr(doc, "passing_score", 60),
        "total_questions": len(questions),
        "questions":       questions,
    }
