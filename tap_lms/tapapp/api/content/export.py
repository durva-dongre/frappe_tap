import frappe
import json
import re

_YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|v/))([A-Za-z0-9_\-]{11})"
)


def _yt(url):
    if not url:
        return None
    m = _YT_RE.search(url)
    return m.group(1) if m else None


def _c(d):
    return {k: v for k, v in d.items() if v is not None and v != "" and v != [] and v != {}}


def _strip_html(s):
    if not s:
        return None
    t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _lang_name(lang_code):
    if not lang_code or lang_code == "en":
        return None
    row = frappe.db.sql(
        'SELECT name FROM "tabTAP Language" WHERE language_code = %s LIMIT 1',
        lang_code,
        as_dict=True,
    )
    return row[0].name if row else None


def _lang_full_name(lang_code):
    row = frappe.db.sql(
        'SELECT language_name FROM "tabTAP Language" WHERE language_code = %s LIMIT 1',
        lang_code,
        as_dict=True,
    )
    if row and row[0].language_name:
        return row[0].language_name
    return "English"


def _build_quiz(quiz_name, lang_name, counters):
    if not quiz_name:
        return None

    row = frappe.db.sql(
        'SELECT name, quiz_name FROM "tabQuiz" WHERE name = %s LIMIT 1',
        quiz_name,
        as_dict=True,
    )
    if not row:
        return None

    nm = row[0].quiz_name

    if lang_name:
        tr = frappe.db.sql(
            'SELECT translated_name FROM "tabQuizTranslation"'
            ' WHERE parent = %s AND language = %s LIMIT 1',
            (quiz_name, lang_name),
            as_dict=True,
        )
        if tr and tr[0].translated_name:
            nm = tr[0].translated_name

    qs_raw = frappe.db.sql(
        'SELECT qq.name AS q_name, qq.question, qq.correct_option, qq.explanation, qq.hint'
        ' FROM "tabQuizQuestionList" ql'
        ' JOIN "tabQuizQuestion" qq ON qq.name = ql.question'
        ' WHERE ql.parent = %s ORDER BY ql.question_number ASC',
        quiz_name,
        as_dict=True,
    )

    questions = []
    for qr in qs_raw:
        q_text = qr.question
        exp = _strip_html(qr.explanation)
        hint = qr.hint

        if lang_name:
            qtr = frappe.db.sql(
                'SELECT translated_question, translated_explanation, translated_hint'
                ' FROM "tabQuizQuestionTranslation"'
                ' WHERE parent = %s AND language = %s LIMIT 1',
                (qr.q_name, lang_name),
                as_dict=True,
            )
            if qtr:
                q_text = qtr[0].translated_question or q_text
                exp = _strip_html(qtr[0].translated_explanation) or exp
                hint = qtr[0].translated_hint or hint

        opts_raw = frappe.db.sql(
            'SELECT CAST(qo.name AS VARCHAR) AS opt_name, qo.option_text, qo.option_number'
            ' FROM "tabQuizOptionList" ol'
            ' JOIN "tabQuizOption" qo ON CAST(qo.name AS VARCHAR) = ol.options'
            ' WHERE ol.parent = %s ORDER BY qo.option_number ASC',
            qr.q_name,
            as_dict=True,
        )

        opts = {}
        correct_id = None
        for o in opts_raw:
            text = o.option_text
            if lang_name:
                otr = frappe.db.sql(
                    'SELECT translated_option FROM "tabQuizOptionTranslation"'
                    ' WHERE parent = %s AND parenttype = %s AND language = %s LIMIT 1',
                    (o.opt_name, "QuizOption", lang_name),
                    as_dict=True,
                )
                if otr and otr[0].translated_option:
                    text = otr[0].translated_option
            opts[str(o.option_number)] = text
            if o.option_number == qr.correct_option:
                correct_id = str(o.option_number)

        questions.append(_c({
            "q": q_text,
            "opts": opts or None,
            "ans": correct_id,
            "hint": hint,
            "exp": exp,
        }))

    counters["quiz_seq"] += 1
    return _c({"id": counters["quiz_seq"], "nm": nm, "qs": questions})


def _build_video(vc_name, lang_name, counters):
    row = frappe.db.sql(
        'SELECT name, video_name, description, video_youtube_url, points'
        ' FROM "tabVideoClass" WHERE name = %s LIMIT 1',
        vc_name,
        as_dict=True,
    )
    if not row:
        return None

    v = row[0]
    nm = v.video_name
    desc = _strip_html(v.description)
    yt = _yt(v.video_youtube_url)
    pts = v.points or 10

    if lang_name:
        tr = frappe.db.sql(
            'SELECT translated_name, translated_description, video_youtube_url'
            ' FROM "tabVideoTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (vc_name, lang_name),
            as_dict=True,
        )
        if tr:
            t = tr[0]
            nm = t.translated_name or nm
            desc = _strip_html(t.translated_description) or desc
            if t.video_youtube_url:
                yt = _yt(t.video_youtube_url)

    plio_quiz = None
    pq_row = frappe.db.sql(
        'SELECT assessment FROM "tabAssessmentList"'
        ' WHERE parent = %s AND assessment_type = \'Quiz\' ORDER BY idx ASC LIMIT 1',
        vc_name,
        as_dict=True,
    )
    if pq_row and pq_row[0].assessment:
        plio_quiz = _build_quiz(pq_row[0].assessment, lang_name, counters)

    counters["vid_seq"] += 1
    return _c({
        "id": counters["vid_seq"],
        "nm": nm,
        "desc": desc,
        "yt": yt,
        "pts": pts,
        "pq": plio_quiz,
    })


def _build_submission_rules(a_name, lang_full_name):
    rows = frappe.db.sql(
        'SELECT submission_label, submission_title, allowed_submission_types,'
        ' guided_text, unguided_text, valid_criteria, invalid_criteria, display_order'
        ' FROM "tabAssignment Submission Rule"'
        ' WHERE parent = %s AND language = %s ORDER BY display_order ASC',
        (a_name, lang_full_name),
        as_dict=True,
    )
    if not rows and lang_full_name != "English":
        rows = frappe.db.sql(
            'SELECT submission_label, submission_title, allowed_submission_types,'
            ' guided_text, unguided_text, valid_criteria, invalid_criteria, display_order'
            ' FROM "tabAssignment Submission Rule"'
            ' WHERE parent = %s AND language = \'English\' ORDER BY display_order ASC',
            a_name,
            as_dict=True,
        )

    steps = []
    for r in rows:
        steps.append(_c({
            "step": r.display_order,
            "label": r.submission_label,
            "sub_title": r.submission_title,
            "sub_types": r.allowed_submission_types,
            "guided_text": _strip_html(r.guided_text),
            "unguided_text": _strip_html(r.unguided_text),
            "valid_criteria": r.valid_criteria,
            "invalid_criteria": r.invalid_criteria,
        }))
    return steps


def _build_assignment(a_name, lang_full_name, counters):
    row = frappe.db.sql(
        'SELECT name, assignment_name, description, assignment_type,'
        ' difficulty_tier, estimated_duration, max_score'
        ' FROM "tabAssignment" WHERE name = %s LIMIT 1',
        a_name,
        as_dict=True,
    )
    if not row:
        return None

    a = row[0]
    nm = a.assignment_name
    desc = _strip_html(a.description)

    if lang_full_name and lang_full_name != "English":
        tr = frappe.db.sql(
            'SELECT translated_title, translated_description'
            ' FROM "tabAssignmentTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (a_name, lang_full_name),
            as_dict=True,
        )
        if tr:
            t = tr[0]
            nm = t.translated_title or nm
            desc = _strip_html(t.translated_description) or desc

    steps = _build_submission_rules(a_name, lang_full_name or "English")

    counters["assign_seq"] += 1
    return _c({
        "id": a.name.replace(" ", "-"),
        "seq": counters["assign_seq"],
        "nm": nm,
        "desc": desc,
        "type": a.assignment_type,
        "diff": a.difficulty_tier,
        "duration": a.estimated_duration,
        "steps": steps or None,
    })


def _build_unit(lu_name, lang_name, counters):
    row = frappe.db.sql(
        'SELECT name, unit_name, description, real_world_connection, difficulty_tier, status'
        ' FROM "tabLearningUnit" WHERE name = %s LIMIT 1',
        lu_name,
        as_dict=True,
    )
    if not row:
        return None

    lu = row[0]
    if lu.status and lu.status != "Published":
        return None

    nm = lu.unit_name
    desc = _strip_html(lu.description)
    rwc = lu.real_world_connection

    if lang_name:
        tr = frappe.db.sql(
            'SELECT translated_name, translated_description, translated_real_world_connection'
            ' FROM "tabLearningUnitTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (lu_name, lang_name),
            as_dict=True,
        )
        if tr:
            t = tr[0]
            nm = t.translated_name or nm
            desc = _strip_html(t.translated_description) or desc
            rwc = t.translated_real_world_connection or rwc

    content_items = frappe.db.sql(
        'SELECT content_type, content FROM "tabUnitContentItem" WHERE parent = %s ORDER BY idx ASC',
        lu_name,
        as_dict=True,
    )

    videos = []
    unit_quiz = None
    for ci in content_items:
        ct = (ci.get("content_type") or "").strip().lower()
        content_ref = ci.get("content")
        if not content_ref:
            continue
        if ct == "videoclass":
            vobj = _build_video(content_ref, lang_name, counters)
            if vobj:
                videos.append(vobj)
        elif ct == "quiz" and unit_quiz is None:
            unit_quiz = _build_quiz(content_ref, lang_name, counters)

    vid_xp = sum(v.get("pts", 0) for v in videos)
    quiz_xp = (videos[-1].get("pts", 10) if videos else 10) if unit_quiz else 0

    return _c({
        "nm": nm,
        "desc": desc,
        "rwc": rwc,
        "diff": lu.difficulty_tier,
        "xp": vid_xp + quiz_xp,
        "vids": videos or None,
        "quiz": unit_quiz,
    })


def _build_course(cl_name, lang_name, counters):
    row = frappe.db.sql(
        'SELECT name, name1, level, vertical, stage, kit_less,'
        ' course_description, course_summary, course_objectives, prerequisite_knowledge, download_url'
        ' FROM "tabCourse Level" WHERE name = %s LIMIT 1',
        cl_name,
        as_dict=True,
    )
    if not row:
        return None

    cl = row[0]
    nm = cl.name1
    desc = _strip_html(cl.course_description)
    summary = cl.course_summary
    obj = _strip_html(cl.course_objectives)
    pre = _strip_html(cl.prerequisite_knowledge)
    dl = cl.download_url

    if lang_name:
        tr = frappe.db.sql(
            'SELECT translated_name, translated_course_description, translated_course_summary,'
            ' translated_course_objectives, translated_prerequisite_knowledge, translated_download_url'
            ' FROM "tabCourse_LevelTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (cl_name, lang_name),
            as_dict=True,
        )
        if tr:
            t = tr[0]
            nm = t.translated_name or nm
            desc = _strip_html(t.translated_course_description) or desc
            summary = t.translated_course_summary or summary
            obj = _strip_html(t.translated_course_objectives) or obj
            pre = _strip_html(t.translated_prerequisite_knowledge) or pre
            dl = t.translated_download_url or dl

    lu_rows = frappe.db.sql(
        'SELECT learning_unit FROM "tabLearningUnitList" WHERE parent = %s ORDER BY idx ASC',
        cl_name,
        as_dict=True,
    )

    units = []
    for r in lu_rows:
        u = _build_unit(r.learning_unit, lang_name, counters)
        if u:
            units.append(u)

    return _c({
        "id": cl.name.replace(" ", "-"),
        "nm": nm,
        "lvl": cl.level,
        "vrt": cl.vertical,
        "stage": cl.stage,
        "kit_less": bool(cl.kit_less),
        "desc": desc,
        "sum": summary,
        "obj": obj,
        "pre": pre,
        "dl": dl,
        "units": units or None,
    })


def _build_index_entry(cl_name, lang_name):
    row = frappe.db.sql(
        'SELECT name, name1, level, vertical, stage, kit_less, course_summary'
        ' FROM "tabCourse Level" WHERE name = %s LIMIT 1',
        cl_name,
        as_dict=True,
    )
    if not row:
        return None

    cl = row[0]
    nm = cl.name1
    summary = cl.course_summary

    if lang_name:
        tr = frappe.db.sql(
            'SELECT translated_name, translated_course_summary'
            ' FROM "tabCourse_LevelTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (cl_name, lang_name),
            as_dict=True,
        )
        if tr:
            t = tr[0]
            nm = t.translated_name or nm
            summary = t.translated_course_summary or summary

    unit_count = frappe.db.count(
        "LearningUnitList", {"parent": cl_name, "parenttype": "Course Level"}
    )

    return _c({
        "id": cl.name.replace(" ", "-"),
        "nm": nm,
        "lvl": cl.level,
        "vrt": cl.vertical,
        "stage": cl.stage,
        "kit_less": bool(cl.kit_less),
        "sum": summary,
        "units_count": unit_count,
    })


def _build_constants(program_id):
    vid_pts = frappe.db.sql(
        'SELECT COALESCE(MIN(vc.points), 10) AS mn'
        ' FROM "tabVideoClass" vc'
        ' JOIN "tabUnitContentItem" uci ON uci.content = vc.name AND uci.content_type = \'VideoClass\''
        ' JOIN "tabLearningUnitList" lul ON lul.learning_unit = uci.parent'
        ' JOIN "tabCourse Level" cl ON cl.name = lul.parent'
        ' WHERE cl.program = %s',
        program_id,
        as_dict=True,
    )
    default = int((vid_pts[0].get("mn") if vid_pts else None) or 10)
    return {"vid_pts": default, "quiz_pts": default, "plio_pts": default}


def _build_languages():
    rows = frappe.db.sql(
        'SELECT language_code, language_name, glific_language_id FROM "tabTAP Language" ORDER BY language_code',
        as_dict=True,
    )
    return [
        _c({
            "id": r.language_code,
            "code": r.language_code,
            "name": r.language_name,
            "glific_id": r.glific_language_id,
        })
        for r in rows
    ]


def _build_states():
    rows = frappe.db.sql(
        'SELECT name, state_name, country FROM "tabState" ORDER BY state_name',
        as_dict=True,
    )
    return [_c({"id": r.name, "name": r.state_name, "country": r.country}) for r in rows]


def _build_districts():
    rows = frappe.db.sql(
        'SELECT d.name, d.district_name, d.state FROM "tabDistrict" d ORDER BY d.state, d.district_name',
        as_dict=True,
    )
    by_state = {}
    for r in rows:
        key = r.state or "__none__"
        by_state.setdefault(key, []).append(_c({"id": r.name, "name": r.district_name}))
    return by_state


def _parse_json_field(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _build_content_item(row):
    return _c({
        "id": row.name,
        "title": row.title,
        "type": row.type,
        "image_url": row.image_url,
        "published_date": str(row.published_date) if row.published_date else None,
        "authors": _parse_json_field(row.authors),
        "content": row.content,
        "location": row.location,
        "event_start": str(row.event_start) if row.event_start else None,
        "event_end": str(row.event_end) if row.event_end else None,
        "speakers": _parse_json_field(row.speakers),
        "event_content_items": _parse_json_field(row.event_content_items),
    })


@frappe.whitelist()
def export_program_content(program_id=None, include_r2=False, langs=None):
    fd = frappe.form_dict
    program_id = program_id or fd.get("program_id")
    langs_raw = langs or fd.get("langs")

    if not program_id:
        frappe.throw("program_id is required", frappe.ValidationError)

    if langs_raw:
        lang_list = [
            l.strip()
            for l in (langs_raw if isinstance(langs_raw, str) else ",".join(langs_raw)).split(",")
            if l.strip()
        ]
    else:
        rows = frappe.db.sql('SELECT language_code FROM "tabTAP Language" ORDER BY language_code', as_list=True)
        lang_list = [r[0] for r in rows] or ["en"]

    course_ids = [
        r.name
        for r in frappe.db.sql(
            'SELECT name FROM "tabCourse Level" WHERE program = %s ORDER BY name ASC',
            program_id,
            as_dict=True,
        )
    ]

    if not course_ids:
        return {"success": False, "error": f"No course levels found for program '{program_id}'"}

    lang_name_cache = {lc: _lang_name(lc) for lc in lang_list}
    lang_full_name_cache = {lc: _lang_full_name(lc) for lc in lang_list}

    assignment_ids = [
        r.name
        for r in frappe.db.sql('SELECT name FROM "tabAssignment" ORDER BY name ASC', as_dict=True)
    ]

    payload = {
        "constants": _build_constants(program_id),
        "languages": _build_languages(),
        "states": _build_states(),
        "districts": _build_districts(),
        "langs": {},
    }

    for lang in lang_list:
        ln = lang_name_cache[lang]
        lfn = lang_full_name_cache[lang]
        counters = {"vid_seq": 0, "quiz_seq": 0, "assign_seq": 0}

        index_courses = [e for e in (_build_index_entry(cid, ln) for cid in course_ids) if e]

        courses = {}
        for cid in course_ids:
            data = _build_course(cid, ln, counters)
            if data:
                courses[cid] = data

        assignments = {}
        assignment_index = []
        for aid in assignment_ids:
            data = _build_assignment(aid, lfn, counters)
            if data:
                assignments[data["id"]] = data
                assignment_index.append(_c({
                    "id": data["id"],
                    "nm": data["nm"],
                    "type": data.get("type"),
                    "diff": data.get("diff"),
                }))

        payload["langs"][lang] = {
            "index": {"courses": index_courses, "assignments": assignment_index},
            "courses": courses,
            "assignments": assignments,
        }

    return {"success": True, "program": program_id, "payload": payload}


@frappe.whitelist()
def export_content():
    rows = frappe.db.sql(
        'SELECT name, title, type, image_url, published_date, authors, content,'
        ' location, event_start, event_end, speakers, event_content_items'
        ' FROM "tabCitizenship Content"'
        ' ORDER BY published_date DESC',
        as_dict=True,
    )

    content = [_build_content_item(r) for r in rows]

    return {"success": True, "payload": {"content": content}}