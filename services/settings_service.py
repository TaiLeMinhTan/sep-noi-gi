import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from database import get_db


DEFAULTS = {
    "openai_model": "gpt-5.6-luna",
    "openai_image_model": "gpt-image-2",
    "openai_vision_model": "gpt-5.6-luna",

    "openai_image_quality": "medium",
    "openai_image_size": "1024x1024",
    "openai_image_compression": "82",

    "visual_match_threshold": "98",
    "visual_max_attempts": "2",
    "visual_total_max_attempts": "4",

    "admin_monthly_budget_usd": "20",
    "usd_vnd_rate": "26000",
}


ENV_FALLBACKS = {
    "openai_model": "OPENAI_MODEL",
    "openai_image_model": "OPENAI_IMAGE_MODEL",
    "openai_vision_model": "OPENAI_VISION_MODEL",

    "openai_image_quality": "OPENAI_IMAGE_QUALITY",
    "openai_image_size": "OPENAI_IMAGE_SIZE",
    "openai_image_compression": "OPENAI_IMAGE_COMPRESSION",

    "visual_match_threshold": "VISUAL_MATCH_THRESHOLD",
    "visual_max_attempts": "VISUAL_MAX_ATTEMPTS",
    "visual_total_max_attempts": "VISUAL_TOTAL_MAX_ATTEMPTS",

    "admin_monthly_budget_usd": "ADMIN_MONTHLY_BUDGET_USD",
    "usd_vnd_rate": "USD_VND_RATE",
}


def _fernet():
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)

    return Fernet(key)


def get_setting(key, default=None):
    db = get_db()

    row = db.execute(
        """
        SELECT value, is_secret
        FROM app_settings
        WHERE key=?
        """,
        (key,),
    ).fetchone()

    if row:
        return row["value"]

    env_name = ENV_FALLBACKS.get(key)

    if env_name:
        env_value = os.getenv(env_name)

        if env_value not in (None, ""):
            return env_value

    if default is not None:
        return default

    return DEFAULTS.get(key)


def set_setting(
    key,
    value,
    is_secret=False,
):
    db = get_db()

    db.execute(
        """
        INSERT INTO app_settings(
            key,
            value,
            is_secret,
            updated_at
        )
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(key)
        DO UPDATE SET
            value=excluded.value,
            is_secret=excluded.is_secret,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            key,
            str(value),
            1 if is_secret else 0,
        ),
    )

    db.commit()


def set_openai_api_key(api_key):
    api_key = (api_key or "").strip()

    if not api_key:
        return

    encrypted = _fernet().encrypt(
        api_key.encode("utf-8")
    ).decode("utf-8")

    set_setting(
        "openai_api_key",
        encrypted,
        is_secret=True,
    )


def get_openai_api_key():
    db = get_db()

    row = db.execute(
        """
        SELECT value
        FROM app_settings
        WHERE key='openai_api_key'
        """
    ).fetchone()

    if row and row["value"]:
        try:
            return _fernet().decrypt(
                row["value"].encode("utf-8")
            ).decode("utf-8")

        except InvalidToken:
            return ""

    return os.getenv(
        "OPENAI_API_KEY",
        "",
    ).strip()


def has_openai_api_key():
    return bool(
        get_openai_api_key()
    )


def masked_api_key():
    key = get_openai_api_key()

    if not key:
        return "Not configured"

    if len(key) <= 10:
        return "••••••••"

    return (
        key[:7]
        + "••••••••••••"
        + key[-4:]
    )


def get_ai_config():
    return {
        "api_key_configured":
            has_openai_api_key(),

        "api_key_masked":
            masked_api_key(),

        "openai_model":
            get_setting(
                "openai_model",
                "gpt-5.6-luna",
            ),

        "openai_image_model":
            get_setting(
                "openai_image_model",
                "gpt-image-2",
            ),

        "openai_vision_model":
            get_setting(
                "openai_vision_model",
                "gpt-5.6-luna",
            ),

        "openai_image_quality":
            get_setting(
                "openai_image_quality",
                "medium",
            ),

        "openai_image_size":
            get_setting(
                "openai_image_size",
                "1024x1024",
            ),

        "openai_image_compression":
            int(
                get_setting(
                    "openai_image_compression",
                    "82",
                )
            ),

        "visual_match_threshold":
            int(
                get_setting(
                    "visual_match_threshold",
                    "98",
                )
            ),

        "visual_max_attempts":
            int(
                get_setting(
                    "visual_max_attempts",
                    "2",
                )
            ),

        "visual_total_max_attempts":
            int(
                get_setting(
                    "visual_total_max_attempts",
                    "4",
                )
            ),

        "admin_monthly_budget_usd":
            float(
                get_setting(
                    "admin_monthly_budget_usd",
                    "20",
                )
            ),

        "usd_vnd_rate":
            float(
                get_setting(
                    "usd_vnd_rate",
                    "26000",
                )
            ),
    }


def save_ai_config(data):
    api_key = (
        data.get("openai_api_key")
        or ""
    ).strip()

    if api_key:
        set_openai_api_key(api_key)

    set_setting(
        "openai_model",
        data.get("openai_model")
        or "gpt-5.6-luna",
    )

    set_setting(
        "openai_image_model",
        data.get("openai_image_model")
        or "gpt-image-2",
    )

    set_setting(
        "openai_vision_model",
        data.get("openai_vision_model")
        or "gpt-5.6-luna",
    )

    set_setting(
        "openai_image_quality",
        data.get("openai_image_quality")
        or "medium",
    )

    set_setting(
        "openai_image_size",
        data.get("openai_image_size")
        or "1024x1024",
    )

    set_setting(
        "openai_image_compression",
        data.get("openai_image_compression")
        or "82",
    )

    set_setting(
        "visual_match_threshold",
        data.get("visual_match_threshold")
        or "98",
    )

    set_setting(
        "visual_max_attempts",
        data.get("visual_max_attempts")
        or "2",
    )

    set_setting(
        "visual_total_max_attempts",
        data.get("visual_total_max_attempts")
        or "4",
    )

    set_setting(
        "admin_monthly_budget_usd",
        data.get("admin_monthly_budget_usd")
        or "20",
    )

    set_setting(
        "usd_vnd_rate",
        data.get("usd_vnd_rate")
        or "26000",
    )

    return get_ai_config()