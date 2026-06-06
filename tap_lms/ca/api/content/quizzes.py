import frappe

LABELS = "ABCDEFGHIJ"


def _parse_fields(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


def _assemble_quizzes_bulk(quiz_ids, lang, optional=None):
    if not quiz_ids:
        return {}

    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    q_list_rows = frappe.get_all(
        "QuizQuestionList",
        filters={"parent": ["in", quiz_ids]},
        fields=["parent", "question", "question_number", "idx"],
        order_by="parent asc, idx asc",
    )

    quiz_questions_map = {}
    question_ids = []
    for r in q_list_rows:
        if r.question:
            quiz_questions_map.setdefault(r.parent, []).append(r)
            question_ids.append(r.question)

    question_ids = list(dict.fromkeys(question_ids))

    if not question_ids:
        return {}

    q_rows = frappe.get_all(
        "QuizQuestion",
        filters={"name": ["in", question_ids]},
        fields=["name", "question", "question_type", "correct_option", "explanation", "hint"],
    )
    question_map = {r.name: r for r in q_rows}

    opt_list_rows = frappe.get_all(
        "QuizOptionList",
        filters={"parent": ["in", question_ids]},
        fields=["parent", "options", "order_number", "idx"],
        order_by="parent asc, order_number asc, idx asc",
    )

    question_options_map = {}
    option_ids = []
    for r in opt_list_rows:
        if r.options:
            question_options_map.setdefault(r.parent, []).append(r)
            option_ids.append(r.options)

    option_ids = list(dict.fromkeys(option_ids))

    opt_text_map = {}
    if option_ids:
        opt_rows = frappe.get_all(
            "QuizOption",
            filters={"name": ["in", option_ids]},
            fields=["name", "option_text"],
        )
        opt_text_map = {r.name: r.option_text for r in opt_rows}

    q_trans_map = {}
    if lang and lang.lower() not in ("en", "english") and question_ids:
        qt_rows = frappe.get_all(
            "QuizQuestionTranslation",
            filters={"parent": ["in", question_ids], "language": lang},
            fields=["parent", "translated_question", "translated_explanation", "translated_hint"],
        )
        q_trans_map = {r.parent: r for r in qt_rows}

    opt_trans_map = {}
    if lang and lang.lower() not in ("en", "english") and option_ids:
        ot_rows = frappe.get_all(
            "QuizOptionTranslation",
            filters={"parent": ["in", option_ids], "language": lang},
            fields=["parent", "translated_option"],
        )
        opt_trans_map = {r.parent: r.translated_option for r in ot_rows}

    def _build_question(q_id):
        q = question_map.get(q_id)
        if not q:
            return None

        qt = q_trans_map.get(q_id)

        options = {}
        correct_letter = ""
        correct_idx_int = int(q.correct_option or 0)

        for enum_idx, opt_row in enumerate(question_options_map.get(q_id, [])):
            opt_id = opt_row.options
            eng_text = opt_text_map.get(opt_id, "")
            translated_text = opt_trans_map.get(opt_id)
            display_text = translated_text or eng_text

            letter = LABELS[enum_idx] if enum_idx < len(LABELS) else str(enum_idx)
            options[letter] = display_text

            if (enum_idx + 1) == correct_idx_int:
                correct_letter = letter

        question_obj = {
            "id": q.name,
            "text": (qt.translated_question if qt and qt.translated_question else None) or q.question or "",
            "question_type": q.question_type,
            "options": options,
            "correct_option": correct_letter,
        }
        if _want("explanation"):
            question_obj["explanation"] = (
                (qt.translated_explanation if qt and qt.translated_explanation else None)
                or q.explanation
            )
        if _want("hint"):
            question_obj["hint"] = (
                (qt.translated_hint if qt and qt.translated_hint else None)
                or q.hint
            )
        return question_obj

    return {
        "quiz_questions": {
            qid: [
                q_obj
                for row in quiz_questions_map.get(qid, [])
                for q_obj in [_build_question(row.question)]
                if q_obj is not None
            ]
            for qid in quiz_ids
        }
    }


@frappe.whitelist(allow_guest=True)
def get_quiz(quiz_id=None, lang=None, fields=None):
    quiz_id = quiz_id or frappe.form_dict.get("quiz_id")
    if not quiz_id:
        frappe.throw("quiz_id is required", frappe.ValidationError)

    optional = _parse_fields(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    doc = frappe.get_doc("Quiz", quiz_id)

    quiz_trans = None
    if lang and lang.lower() not in ("en", "english"):
        for row in (doc.translations or []):
            if row.language == lang:
                quiz_trans = row
                break

    quiz_title = (
        (quiz_trans.translated_name if quiz_trans and quiz_trans.translated_name else None)
        or doc.quiz_name
    )
    quiz_description = (
        (quiz_trans.translated_description if quiz_trans and quiz_trans.translated_description else None)
        or doc.description
    ) if _want("description") else None

    bulk_result = _assemble_quizzes_bulk([quiz_id], lang, optional)
    questions = bulk_result["quiz_questions"].get(quiz_id, [])

    response = {
        "id": doc.name,
        "title": quiz_title,
        "eng_name": doc.quiz_name,
        "passing_score": doc.passing_score or 60,
        "time_limit": str(doc.time_limit) if doc.time_limit else None,
        "max_attempts": doc.max_attempts,
        "total_questions": len(questions),
        "questions": questions,
    }

    if _want("description"):
        response["description"] = quiz_description

    return response