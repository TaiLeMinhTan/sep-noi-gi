import hashlib
import json
import os
from pathlib import Path

from flask import current_app

from ai_service import (
    AIServiceError,
    build_visual_prompt,
    check_visual_match,
    generate_visual_image,
    image_model_name,
    is_configured,
    save_visual_file,
    vision_model_name,
    visual_max_attempts,
    visual_threshold,
    visual_total_max_attempts,
)
from database import get_db
from services.cost_service import record_usage


def _asset_dict(row):
    if not row:
        return None
    return {
        "visual_asset_id": row["id"],
        "status": row["status"],
        "image_url": row["image_path"],
        "match_score": row["match_score"],
        "generation_count": row["generation_count"],
        "accepted_attempt": row["accepted_attempt"],
        "qa": json.loads(row["qa_json"]) if row["qa_json"] else None,
        "image_model": row["image_model"],
        "vision_model": row["vision_model"],
        "total_tokens": row["total_tokens"] or 0,
        "last_error": row["last_error"],
    }


def get_visual_status(lesson_id):
    db = get_db()
    row = db.execute("SELECT * FROM visual_assets WHERE lesson_id=?", (lesson_id,)).fetchone()
    if not row:
        return {"status": "missing", "image_url": None, "match_score": None, "generation_count": 0}
    return _asset_dict(row)


def _ensure_asset(db, lesson_id, sentence, context_key, prompt):
    row = db.execute("SELECT * FROM visual_assets WHERE lesson_id=?", (lesson_id,)).fetchone()
    if row:
        return row
    key_raw = f"{lesson_id}|{context_key}|{sentence}".encode("utf-8")
    visual_key = hashlib.sha256(key_raw).hexdigest()[:24]
    db.execute(
        """INSERT INTO visual_assets(lesson_id,visual_key,status,image_model,vision_model,prompt)
           VALUES(?,?,?,?,?,?)""",
        (lesson_id, visual_key, "pending", image_model_name(), vision_model_name(), prompt),
    )
    db.commit()
    return db.execute("SELECT * FROM visual_assets WHERE lesson_id=?", (lesson_id,)).fetchone()


def _relative_static_url(filename):
    return f"/static/generated/visuals/{filename}"


def _save_accepted(image_bytes, visual_key):
    filename = f"{visual_key}.webp"
    out_dir = Path(current_app.static_folder) / "generated" / "visuals"
    save_visual_file(image_bytes, str(out_dir), filename)
    return _relative_static_url(filename)


def create_or_get_visual(lesson_id, user_id=None):
    db = get_db()
    lesson_row = db.execute(
        """SELECT l.id lesson_id,l.context_key,l.lesson_json,l.image_prompt,l.image_path,
                  s.original_text sentence
           FROM lessons l JOIN sentences s ON s.id=l.sentence_id WHERE l.id=?""",
        (lesson_id,),
    ).fetchone()
    if not lesson_row:
        raise AIServiceError("Lesson không tồn tại.")

    existing = db.execute("SELECT * FROM visual_assets WHERE lesson_id=?", (lesson_id,)).fetchone()
    if existing and existing["status"] == "accepted" and existing["image_path"]:
        result = _asset_dict(existing)
        result["cache_hit"] = True
        return result

    if not is_configured():
        raise AIServiceError("Chưa có OPENAI_API_KEY nên chưa thể sinh ảnh. Lesson text vẫn dùng được.")

    lesson = json.loads(lesson_row["lesson_json"])
    sentence = lesson.get("sentence") or lesson_row["sentence"]
    context_key = lesson_row["context_key"] or lesson.get("context") or "general"
    visual_spec = lesson.get("visual_spec") or {
        "entities": ["subjects mentioned in the sentence"],
        "action": lesson.get("visual") or sentence,
        "environment": context_key,
        "must_show": [lesson.get("visual") or sentence],
        "must_not_show": ["visible text", "unrelated actions"],
        "camera": "simple medium shot focused on the main action",
    }
    base_prompt = lesson.get("image_prompt") or lesson_row["image_prompt"] or lesson.get("visual") or sentence
    initial_prompt = build_visual_prompt(sentence, context_key, visual_spec, base_prompt)
    asset = _ensure_asset(db, lesson_id, sentence, context_key, initial_prompt)

    if int(asset["generation_count"] or 0) >= visual_total_max_attempts():
        return {
            "status": asset["status"], "image_url": asset["image_path"],
            "match_score": asset["match_score"], "cache_hit": True,
            "generation_count": asset["generation_count"],
            "threshold": visual_threshold(),
            "last_error": f"Đã chạm giới hạn tổng {visual_total_max_attempts()} lần sinh ảnh cho lesson này. Reset visual trong DB nếu muốn thử lại có chủ đích.",
        }

    # A previous failed run is retryable. We intentionally cap attempts per request and total attempts.
    correction = ""
    best = None
    best_bytes = None
    start_attempt = int(asset["generation_count"] or 0) + 1
    remaining = max(0, visual_total_max_attempts() - int(asset["generation_count"] or 0))
    max_this_run = min(visual_max_attempts(), remaining)

    db.execute(
        "UPDATE visual_assets SET status='generating',last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (asset["id"],),
    )
    db.commit()

    try:
        for offset in range(max_this_run):
            attempt_no = start_attempt + offset
            prompt = build_visual_prompt(sentence, context_key, visual_spec, base_prompt, correction)
            image_bytes, gen_usage = generate_visual_image(prompt)
            record_usage(user_id=user_id, event_type="image_generation", model=image_model_name(),
                         lesson_id=lesson_id, visual_asset_id=asset["id"], request_id=gen_usage.get("response_id"),
                         input_tokens=gen_usage.get("input_tokens",0), cached_input_tokens=gen_usage.get("cached_input_tokens",0),
                         output_tokens=0, image_input_tokens=gen_usage.get("image_input_tokens",0),
                         image_output_tokens=gen_usage.get("image_output_tokens",0),
                         metadata={"attempt_no":attempt_no,"quality":os.getenv("OPENAI_IMAGE_QUALITY","medium"),"size":os.getenv("OPENAI_IMAGE_SIZE","1024x1024")})
            qa, qa_usage = check_visual_match(sentence, visual_spec, image_bytes)
            record_usage(user_id=user_id, event_type="vision_qa", model=vision_model_name(),
                         lesson_id=lesson_id, visual_asset_id=asset["id"], request_id=qa_usage.get("response_id"),
                         input_tokens=qa_usage.get("input_tokens",0), cached_input_tokens=qa_usage.get("cached_input_tokens",0),
                         output_tokens=qa_usage.get("output_tokens",0), metadata={"attempt_no":attempt_no})
            score = int(qa.get("score") or 0)
            accepted = (
                score >= visual_threshold()
                and qa.get("entities_match") is True
                and qa.get("action_match") is True
                and qa.get("context_match") is True
                and qa.get("no_conflicting_details") is True
                and qa.get("instant_understanding") is True
            )
            token_total = int(gen_usage.get("total_tokens") or 0) + int(qa_usage.get("total_tokens") or 0)
            db.execute(
                """INSERT INTO visual_attempts(
                       visual_asset_id,attempt_no,prompt,generation_response_id,generation_tokens,
                       qa_response_id,qa_tokens,match_score,accepted,qa_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    asset["id"], attempt_no, prompt, gen_usage.get("response_id"), gen_usage.get("total_tokens"),
                    qa_usage.get("response_id"), qa_usage.get("total_tokens"), score, 1 if accepted else 0,
                    json.dumps(qa, ensure_ascii=False),
                ),
            )
            db.execute(
                """UPDATE visual_assets SET generation_count=generation_count+1,
                       total_tokens=total_tokens+?,match_score=?,qa_json=?,prompt=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (token_total, score, json.dumps(qa, ensure_ascii=False), prompt, asset["id"]),
            )
            db.commit()

            if best is None or score > best["score"]:
                best = {"score": score, "qa": qa, "attempt_no": attempt_no, "prompt": prompt}
                best_bytes = image_bytes

            if accepted:
                image_url = _save_accepted(image_bytes, asset["visual_key"])
                db.execute(
                    """UPDATE visual_assets SET status='accepted',image_path=?,match_score=?,qa_json=?,
                           accepted_attempt=?,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (image_url, score, json.dumps(qa, ensure_ascii=False), attempt_no, asset["id"]),
                )
                db.execute("UPDATE lessons SET image_path=? WHERE id=?", (image_url, lesson_id))
                db.commit()
                row = db.execute("SELECT * FROM visual_assets WHERE id=?", (asset["id"],)).fetchone()
                result = _asset_dict(row)
                result["cache_hit"] = False
                result["threshold"] = visual_threshold()
                return result

            correction = qa.get("regeneration_instruction") or (
                "Make every required entity and the exact action more explicit. Remove conflicting details."
            )

        # Keep no rejected image in the public cache. Save only metadata for debugging/cost tracking.
        score = best["score"] if best else 0
        err = f"Ảnh tốt nhất đạt {score}/100, chưa đạt ngưỡng {visual_threshold()}/100. Có thể thử lại sau."
        db.execute(
            "UPDATE visual_assets SET status='rejected',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (err, asset["id"]),
        )
        db.commit()
        return {
            "status": "rejected", "image_url": None, "match_score": score, "threshold": visual_threshold(),
            "cache_hit": False, "last_error": err, "qa": best["qa"] if best else None,
        }
    except Exception as exc:
        message = str(exc)
        db.execute(
            "UPDATE visual_assets SET status='error',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (message, asset["id"]),
        )
        db.commit()
        if isinstance(exc, AIServiceError):
            raise
        raise AIServiceError(f"Không tạo được visual: {message}") from exc
