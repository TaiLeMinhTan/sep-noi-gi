import json
import re
from datetime import datetime, timedelta

from database import get_db
from ai_service import AIServiceError, generate_lesson, is_configured, model_name
from services.cost_service import record_usage


def normalize(text):
    text = text.strip().lower()
    text = re.sub(r"[“”‘’]", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text


def context_key_from_profile(profile):
    if not profile:
        return "general"
    blob = " ".join(
        str(profile[k] or "")
        for k in ("occupation", "industry", "goals", "situations")
        if k in profile.keys()
    ).lower()
    groups = [
        ("manufacturing", ["engineer", "manufactur", "factory", "test", "technician", "quality", "production", "optical", "fixture"]),
        ("software", ["software", "developer", "program", "it ", "backend", "frontend", "data", "devops"]),
        ("sales", ["sales", "customer", "business development", "quotation", "account manager", "buyer", "purchas"]),
        ("student", ["student", "school", "university", "college", "study"]),
        ("office", ["office", "project", "manager", "hr", "finance", "admin", "meeting"]),
    ]
    for key, words in groups:
        if any(w in blob for w in words):
            return key
    return "general"


def _lesson_row_to_dict(row):
    d = json.loads(row["lesson_json"])
    d["lesson_id"] = row["lesson_id"]
    d["sentence_id"] = row["sentence_id"]
    d["context_key"] = row["context_key"]
    d["ai_model"] = row["ai_model"]
    d["source"] = row["source"]
    d["image_url"] = row["image_path"] if "image_path" in row.keys() else None
    visual = get_db().execute("SELECT status,image_path,match_score,generation_count FROM visual_assets WHERE lesson_id=?", (row["lesson_id"],)).fetchone()
    d["visual_asset"] = dict(visual) if visual else {"status":"missing","image_path":None,"match_score":None,"generation_count":0}
    return d


def _profile_dict(user_id):
    row = get_db().execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else {}


def get_home_payload(user_id):
    db = get_db()

    profile = db.execute(
        "SELECT * FROM profiles WHERE user_id=?",
        (user_id,)
    ).fetchone()

    profile_dict = dict(profile) if profile else {}
    context_key = context_key_from_profile(profile or {})

    rows = db.execute(
        """SELECT l.id lesson_id,s.id sentence_id,l.lesson_json,
                  l.context_key,l.ai_model,l.source,l.image_path
           FROM lessons l
           JOIN sentences s ON s.id=l.sentence_id
           ORDER BY CASE
                WHEN l.context_key=? THEN 0
                WHEN l.context_key='general' THEN 1
                ELSE 2
           END, l.id DESC
           LIMIT 6""",
        (context_key,)
    ).fetchall()

    # +7 hours = giờ Việt Nam.
    # Hôm nay sẽ tự chuyển sang ngày mới lúc 00:00 Việt Nam.
    learned_today = db.execute(
        """SELECT COUNT(*) AS count
           FROM daily_learning
           WHERE user_id=?
             AND activity_date=date('now', '+7 hours')""",
        (user_id,)
    ).fetchone()["count"]

    week_rows = db.execute(
        """WITH RECURSIVE days(day, position) AS (
               SELECT date('now', '+7 hours', '-6 days'), 0
               UNION ALL
               SELECT date(day, '+1 day'), position + 1
               FROM days
               WHERE position < 6
           ),
           daily_count AS (
               SELECT activity_date, COUNT(*) AS completed
               FROM daily_learning
               WHERE user_id=?
                 AND activity_date >= date('now', '+7 hours', '-6 days')
               GROUP BY activity_date
           )
           SELECT
               days.day,
               CASE WHEN COALESCE(daily_count.completed, 0) >= 2
                    THEN 1 ELSE 0 END AS done
           FROM days
           LEFT JOIN daily_count
             ON daily_count.activity_date=days.day
           ORDER BY days.day""",
        (user_id,)
    ).fetchall()

    week_days = [
        {
            "date": row["day"],
            "done": bool(row["done"]),
        }
        for row in week_rows
    ]

    return {
        "profile": profile_dict,
        "context_key": context_key,
        "lessons": [_lesson_row_to_dict(row) for row in rows],
        "stats": {
            "learned_today": learned_today,
            "goal": 2,
            "week_days": week_days,
        },
        "ai": {
            "configured": is_configured(),
            "model": model_name(),
        },
    }


def get_lesson_by_id(lesson_id, user_id):
    db = get_db()
    row = db.execute(
        """SELECT l.id lesson_id,s.id sentence_id,l.lesson_json,l.context_key,l.ai_model,l.source,l.image_path
           FROM lessons l JOIN sentences s ON s.id=l.sentence_id WHERE l.id=?""",
        (lesson_id,),
    ).fetchone()
    if not row:
        return None
    db.execute(
        """INSERT INTO user_learning(user_id,lesson_id,status) VALUES(?,?,?)
           ON CONFLICT(user_id,lesson_id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP""",
        (user_id, lesson_id, "learning"),
    )
    db.commit()
    return _lesson_row_to_dict(row)


def _record_ai_request(db, user_id, sentence, context_key, status, cache_hit, model, usage=None, error=None):
    usage = usage or {}
    db.execute(
        """INSERT INTO ai_requests(
               user_id,sentence_text,context_key,status,cache_hit,ai_model,
               input_tokens,output_tokens,total_tokens,response_id,error_message
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            user_id,
            sentence,
            context_key,
            status,
            1 if cache_hit else 0,
            model,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
            usage.get("response_id"),
            error,
        ),
    )


def _store_patterns(db, sentence_id, payload):
    for p in payload.get("patterns", []):
        pattern = (p.get("pattern") or "").strip()
        if not pattern:
            continue
        examples = p.get("examples") or []
        db.execute(
            """INSERT INTO patterns(pattern,example_json,frequency) VALUES(?,?,1)
               ON CONFLICT(pattern) DO UPDATE SET
                 example_json=excluded.example_json,
                 frequency=patterns.frequency+1""",
            (pattern, json.dumps(examples, ensure_ascii=False)),
        )
        pid = db.execute("SELECT id FROM patterns WHERE pattern=?", (pattern,)).fetchone()["id"]
        db.execute(
            "INSERT OR IGNORE INTO sentence_patterns(sentence_id,pattern_id) VALUES(?,?)",
            (sentence_id, pid),
        )


def create_or_get_lesson(text, user_id):
    db = get_db()
    norm = normalize(text)
    profile = _profile_dict(user_id)
    context_key = context_key_from_profile(profile)

    row = db.execute(
        """SELECT l.id lesson_id,s.id sentence_id,l.lesson_json,l.context_key,l.ai_model,l.source,l.image_path
           FROM sentences s JOIN lessons l ON l.sentence_id=s.id
           WHERE s.normalized_text=? AND l.context_key=?""",
        (norm, context_key),
    ).fetchone()
    if row:
        _record_ai_request(db, user_id, text, context_key, "cache", True, row["ai_model"])
        db.commit()
        result = _lesson_row_to_dict(row)
        result["cache_hit"] = True
        return result

    try:
        payload, usage = generate_lesson(text, profile, context_key)
    except AIServiceError as exc:
        _record_ai_request(db, user_id, text, context_key, "error", False, model_name(), error=str(exc))
        db.commit()
        raise

    sentence_text = (payload.get("sentence") or text).strip()
    canonical_norm = normalize(sentence_text)
    db.execute(
        "INSERT OR IGNORE INTO sentences(original_text,normalized_text,context_category) VALUES(?,?,?)",
        (sentence_text, canonical_norm, context_key),
    )
    sentence_row = db.execute("SELECT id FROM sentences WHERE normalized_text=?", (canonical_norm,)).fetchone()
    sid = sentence_row["id"]

    # A corrected sentence may already have a cached lesson for the same context.
    existing = db.execute(
        """SELECT l.id lesson_id,s.id sentence_id,l.lesson_json,l.context_key,l.ai_model,l.source,l.image_path
           FROM lessons l JOIN sentences s ON s.id=l.sentence_id
           WHERE l.sentence_id=? AND l.context_key=?""",
        (sid, context_key),
    ).fetchone()
    if existing:
        _record_ai_request(db, user_id, text, context_key, "success", False, model_name(), usage)
        db.commit()
        record_usage(user_id=user_id, event_type="lesson_text", model=model_name(), lesson_id=existing["lesson_id"],
                     request_id=usage.get("response_id"), input_tokens=usage.get("input_tokens",0),
                     cached_input_tokens=usage.get("cached_input_tokens",0), output_tokens=usage.get("output_tokens",0),
                     metadata={"context_key": context_key, "generated_but_reused": True})
        result = _lesson_row_to_dict(existing)
        result["cache_hit"] = False
        result["generated_but_reused"] = True
        return result

    cur = db.execute(
        """INSERT INTO lessons(sentence_id,context_key,ai_model,lesson_json,image_prompt,source)
           VALUES(?,?,?,?,?,?)""",
        (
            sid,
            context_key,
            model_name(),
            json.dumps(payload, ensure_ascii=False),
            payload.get("image_prompt"),
            "openai",
        ),
    )
    lesson_id = cur.lastrowid
    _store_patterns(db, sid, payload)
    _record_ai_request(db, user_id, text, context_key, "success", False, model_name(), usage)
    db.commit()
    record_usage(user_id=user_id, event_type="lesson_text", model=model_name(), lesson_id=lesson_id,
                 request_id=usage.get("response_id"), input_tokens=usage.get("input_tokens",0),
                 cached_input_tokens=usage.get("cached_input_tokens",0), output_tokens=usage.get("output_tokens",0),
                 metadata={"context_key": context_key})

    payload.update(
        {
            "lesson_id": lesson_id,
            "sentence_id": sid,
            "context_key": context_key,
            "ai_model": model_name(),
            "source": "openai",
            "cache_hit": False,
            "usage": usage,
        }
    )
    return payload


def mark_progress(user_id, lesson_id, status, score):
    db = get_db()

    db.execute(
        """INSERT INTO user_learning(
                user_id, lesson_id, status, mastery_score, last_seen_at
           )
           VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP)

           ON CONFLICT(user_id, lesson_id)
           DO UPDATE SET
                status=excluded.status,
                mastery_score=excluded.mastery_score,
                last_seen_at=CURRENT_TIMESTAMP""",
        (user_id, lesson_id, status, score),
    )

    # Một câu chỉ được tính một lần trong một ngày.
    if status == "learned":
        db.execute(
            """INSERT OR IGNORE INTO daily_learning(
                    user_id, lesson_id, activity_date
               )
               VALUES(?, ?, date('now', '+7 hours'))""",
            (user_id, lesson_id),
        )

    db.commit()


def record_review(user_id, lesson_id, result):
    db = get_db()
    days = 3 if result == "remembered" else 1
    nxt = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO reviews(user_id,lesson_id,result,next_review_at) VALUES(?,?,?,?)",
        (user_id, lesson_id, result, nxt),
    )
    db.execute(
        """INSERT INTO user_learning(user_id,lesson_id,status,mastery_score) VALUES(?,?,?,?)
           ON CONFLICT(user_id,lesson_id) DO UPDATE SET
             last_seen_at=CURRENT_TIMESTAMP,
             mastery_score=CASE WHEN ?='remembered' THEN MIN(1,mastery_score+.2) ELSE MAX(0,mastery_score-.1) END""",
        (user_id, lesson_id, "reviewing", 0.2, result),
    )
    db.commit()
