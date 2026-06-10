import frappe
import re

_vid_seq = 0
_quiz_seq = 0

def _next_vid():
    global _vid_seq
    _vid_seq += 1
    return _vid_seq

def _next_quiz():
    global _quiz_seq
    _quiz_seq += 1
    return _quiz_seq

def _reset_counters():
    global _vid_seq, _quiz_seq
    _vid_seq = 0
    _quiz_seq = 0

_YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|v/))([A-Za-z0-9_\-]{11})"
)

def _yt(url):
    if not url:
        return None
    m = _YT_RE.search(url)
    return m.group(1) if m else url

def _c(d):
    return {k: v for k, v in d.items() if v is not None and v != "" and v != [] and v != {}}

def _h(s):
    if not s:
        return None
    t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None

def _tr_question(q_name, lang):
    if not lang or lang == "en":
        return {}
    row = frappe.db.sql(
        'SELECT translated_question, translated_explanation, translated_hint FROM "tabQuizQuestionTranslation" WHERE parent = %s AND language = %s LIMIT 1',
        (q_name, lang), as_dict=True,
    )
    return row[0] if row else {}

def _tr_option(opt_name, lang):
    if not lang or lang == "en":
        return None
    row = frappe.db.sql(
        'SELECT translated_option FROM "tabQuizOptionTranslation" WHERE parent = %s AND language = %s LIMIT 1',
        (opt_name, lang), as_dict=True,
    )
    return row[0].translated_option if row and row[0].translated_option else None

def _build_quiz(quiz_name, lang):
    if not quiz_name:
        return None
    row = frappe.db.sql(
        'SELECT quiz_name FROM "tabQuiz" WHERE name = %s LIMIT 1',
        quiz_name, as_dict=True,
    )
    if not row:
        return None
    qs_raw = frappe.db.sql(
        'SELECT qq.name AS q_name, qq.question, qq.correct_option, qq.explanation, qq.hint FROM "tabQuizQuestionList" ql JOIN "tabQuizQuestion" qq ON qq.name = ql.question WHERE ql.parent = %s ORDER BY ql.question_number ASC',
        quiz_name, as_dict=True,
    )
    questions = []
    for qr in qs_raw:
        tr     = _tr_question(qr.q_name, lang)
        q_text = tr.get("translated_question") or qr.question
        exp    = _h(tr.get("translated_explanation") or qr.explanation)
        hint   = tr.get("translated_hint") or qr.hint
        opts_raw = frappe.db.sql(
            'SELECT qo.name AS opt_name, qo.option_text, qo.option_number FROM "tabQuizOptionList" ol JOIN "tabQuizOption" qo ON qo.name = ol.options WHERE ol.parent = %s ORDER BY qo.option_number ASC',
            qr.q_name, as_dict=True,
        )
        opts = {}
        correct_id = None
        for o in opts_raw:
            text = _tr_option(o.opt_name, lang) or o.option_text
            opts[str(o.option_number)] = text
            if o.option_number == qr.correct_option:
                correct_id = str(o.option_number)
        questions.append(_c({"q": q_text, "opts": opts or None, "ans": correct_id, "hint": hint, "exp": exp}))
    return _c({"id": _next_quiz(), "nm": row[0].quiz_name, "qs": questions})

def _build_video(vc_name, lang, include_r2):
    row = frappe.db.sql(
        'SELECT name, video_name, description, video_youtube_url, video_url, video_plio_url, duration, points, plio_at_seconds FROM "tabVideoClass" WHERE name = %s LIMIT 1',
        vc_name, as_dict=True,
    )
    if not row:
        return None
    v       = row[0]
    nm      = v.video_name
    desc    = _h(v.description)
    yt      = _yt(v.video_youtube_url)
    url     = v.video_url if include_r2 else None
    pts     = v.points or 10
    plio_at = int(v.plio_at_seconds) if v.get("plio_at_seconds") else None
    if lang and lang != "en":
        tr = frappe.db.sql(
            'SELECT translated_name, translated_description, video_youtube_url, video_url FROM "tabVideoTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (vc_name, lang), as_dict=True,
        )
        if tr:
            t    = tr[0]
            nm   = t.translated_name or nm
            desc = _h(t.translated_description) or desc
            yt   = _yt(t.video_youtube_url) if t.video_youtube_url else yt
            url  = (t.video_url if include_r2 else None) or url
    plio_quiz = None
    if v.video_plio_url:
        pq_row = frappe.db.sql(
            'SELECT assessment FROM "tabAssessmentList" WHERE parent = %s ORDER BY idx ASC LIMIT 1',
            vc_name, as_dict=True,
        )
        if pq_row and pq_row[0].assessment:
            plio_quiz = _build_quiz(pq_row[0].assessment, lang)
    return _c({"id": _next_vid(), "nm": nm, "desc": desc, "yt": yt, "url": url, "dur": str(v.duration) if v.duration else None, "pts": pts, "plio_at": plio_at, "pq": plio_quiz})

def _build_unit(lu_name, lang, include_r2):
    row = frappe.db.sql(
        'SELECT name, unit_name, description, real_world_connection, difficulty_tier, status FROM "tabLearningUnit" WHERE name = %s LIMIT 1',
        lu_name, as_dict=True,
    )
    if not row:
        return None
    lu = row[0]
    if lu.status and lu.status != "Published":
        return None
    nm   = lu.unit_name
    desc = _h(lu.description)
    rwc  = lu.real_world_connection
    if lang and lang != "en":
        tr = frappe.db.sql(
            'SELECT translated_name, translated_description, translated_real_world_connection FROM "tabLearningUnitTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (lu_name, lang), as_dict=True,
        )
        if tr:
            t    = tr[0]
            nm   = t.translated_name or nm
            desc = _h(t.translated_description) or desc
            rwc  = t.translated_real_world_connection or rwc
    content_items = frappe.db.sql(
        'SELECT content_type, video, quiz, order_index FROM "tabUnitContentItem" WHERE parent = %s ORDER BY order_index ASC',
        lu_name, as_dict=True,
    )
    videos    = []
    unit_quiz = None
    unit_pts  = 10
    for ci in content_items:
        ct = (ci.get("content_type") or "").lower()
        if ci.get("video") and ct in ("", "video"):
            vobj = _build_video(ci.video, lang, include_r2)
            if vobj:
                videos.append(vobj)
                unit_pts = vobj.get("pts", 10)
        if ci.get("quiz") and ct in ("", "quiz"):
            unit_quiz = _build_quiz(ci.quiz, lang)
    if not unit_quiz:
        fb = frappe.db.sql(
            'SELECT quiz FROM "tabUnitContentItem" WHERE parent = %s AND quiz IS NOT NULL LIMIT 1',
            lu_name, as_dict=True,
        )
        if fb:
            unit_quiz = _build_quiz(fb[0].quiz, lang)
    vid_count = len(videos)
    q_count   = len(unit_quiz["qs"]) if unit_quiz and unit_quiz.get("qs") else 0
    total_xp  = sum(v.get("pts", 0) for v in videos) + (unit_pts if unit_quiz else 0)
    return _c({"nm": nm, "desc": desc, "rwc": rwc, "diff": lu.difficulty_tier, "total_xp": total_xp, "vid_count": vid_count, "q_count": q_count, "vids": videos or None, "quiz": unit_quiz})

def _build_course(cl_name, lang, include_r2):
    row = frappe.db.sql(
        'SELECT name, name1, level, vertical, course_description, course_summary, course_image, course_objectives, prerequisite_knowledge, download_url FROM "tabCourse Level" WHERE name = %s LIMIT 1',
        cl_name, as_dict=True,
    )
    if not row:
        return None
    cl      = row[0]
    nm      = cl.name1
    desc    = _h(cl.course_description)
    summary = cl.course_summary
    obj     = _h(cl.course_objectives)
    pre     = _h(cl.prerequisite_knowledge)
    dl      = cl.download_url
    if lang and lang != "en":
        tr = frappe.db.sql(
            'SELECT translated_name, translated_course_description, translated_course_summary, translated_course_objectives, translated_prerequisite_knowledge, translated_download_url FROM "tabCourse_LevelTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (cl_name, lang), as_dict=True,
        )
        if tr:
            t       = tr[0]
            nm      = t.translated_name or nm
            desc    = _h(t.translated_course_description) or desc
            summary = t.translated_course_summary or summary
            obj     = _h(t.translated_course_objectives) or obj
            pre     = _h(t.translated_prerequisite_knowledge) or pre
            dl      = t.translated_download_url or dl
    lu_rows = frappe.db.sql(
        'SELECT learning_unit FROM "tabLearningUnitList" WHERE parent = %s ORDER BY idx ASC',
        cl_name, as_dict=True,
    )
    units = [u for u in (_build_unit(r.learning_unit, lang, include_r2) for r in lu_rows) if u]
    return _c({"id": cl.name, "nm": nm, "lvl": cl.level, "vrt": cl.vertical, "desc": desc, "sum": summary, "img": cl.course_image, "obj": obj, "pre": pre, "dl": dl, "units": units or None})

def _build_index_entry(cl_name, lang):
    row = frappe.db.sql(
        'SELECT name, name1, level, vertical, course_description, course_summary, course_image FROM "tabCourse Level" WHERE name = %s LIMIT 1',
        cl_name, as_dict=True,
    )
    if not row:
        return None
    cl      = row[0]
    nm      = cl.name1
    desc    = _h(cl.course_description)
    summary = cl.course_summary
    if lang and lang != "en":
        tr = frappe.db.sql(
            'SELECT translated_name, translated_course_description, translated_course_summary FROM "tabCourse_LevelTranslation" WHERE parent = %s AND language = %s LIMIT 1',
            (cl_name, lang), as_dict=True,
        )
        if tr:
            t       = tr[0]
            nm      = t.translated_name or nm
            desc    = _h(t.translated_course_description) or desc
            summary = t.translated_course_summary or summary
    return _c({"id": cl.name, "nm": nm, "lvl": cl.level, "vrt": cl.vertical, "desc": desc, "sum": summary, "img": cl.course_image})

def _build_constants(program_id):
    vid_pts = frappe.db.sql(
        'SELECT COALESCE(MIN(vc.points), 10) AS mn FROM "tabVideoClass" vc JOIN "tabUnitContentItem" uci ON uci.video = vc.name JOIN "tabLearningUnitList" lul ON lul.learning_unit = uci.parent JOIN "tabCourse Level" cl ON cl.name = lul.parent WHERE cl.program = %s',
        program_id, as_dict=True,
    )
    default = int((vid_pts[0].get("mn") if vid_pts else None) or 10)
    return {"vid_pts": default, "quiz_pts": default, "plio_pts": default}

@frappe.whitelist()
def export_program_content(program_id=None, include_r2=False, langs=None):
    fd         = frappe.form_dict
    program_id = program_id or fd.get("program_id")
    include_r2 = str(fd.get("include_r2", include_r2)).lower() in ("1", "true", "yes")
    langs_raw  = langs or fd.get("langs")

    if not program_id:
        frappe.throw("program_id is required", frappe.ValidationError)

    if langs_raw:
        lang_list = [
            l.strip()
            for l in (langs_raw if isinstance(langs_raw, str) else ",".join(langs_raw)).split(",")
            if l.strip()
        ]
    else:
        rows      = frappe.db.sql('SELECT language_code FROM "tabTAP Language" ORDER BY language_code', as_list=True)
        lang_list = [r[0] for r in rows] or ["en"]

    course_ids = [
        r.name
        for r in frappe.db.sql(
            'SELECT name FROM "tabCourse Level" WHERE program = %s ORDER BY name ASC',
            program_id, as_dict=True,
        )
    ]

    if not course_ids:
        return {"success": False, "error": f"No course levels found for program '{program_id}'"}

    payload = {"constants": _build_constants(program_id), "langs": {}}

    for lang in lang_list:
        _reset_counters()
        index_courses = [e for e in (_build_index_entry(cid, lang) for cid in course_ids) if e]
        courses = {}
        for cid in course_ids:
            data = _build_course(cid, lang, include_r2)
            if data:
                courses[cid] = data
        payload["langs"][lang] = {"index": {"courses": index_courses}, "courses": courses}

    return {"success": True, "program": program_id, "payload": payload}