import os

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

load_dotenv()


from ai_service import (
    AIServiceError,
    is_configured,
    model_name,
    image_model_name,
    vision_model_name,
    visual_threshold,
    test_openai_connection,
)

from database import (
    get_db,
    init_db,
)

from services.lesson_service import (
    create_or_get_lesson,
    get_home_payload,
    get_lesson_by_id,
    mark_progress,
    record_review,
)

from services.visual_service import (
    create_or_get_visual,
    get_visual_status,
)

from services.cost_service import (
    dashboard_payload,
)

from services.settings_service import (
    get_ai_config,
    save_ai_config,
    get_setting,
)


app = Flask(__name__)

app.config[
    "SECRET_KEY"
] = os.environ.get(
    "SECRET_KEY",
    "dev-secret-change-me",
)

app.config[
    "DATABASE"
] = os.path.join(
    app.instance_path,
    "sep_noigi.db",
)

os.makedirs(
    app.instance_path,
    exist_ok=True,
)

init_db(app)


def ensure_admin():

    email = (
        os.getenv(
            "ADMIN_EMAIL",
            "",
        )
        .strip()
        .lower()
    )

    password = (
        os.getenv(
            "ADMIN_PASSWORD",
            "",
        )
        .strip()
    )

    if (
        not email
        or not password
    ):
        return

    with app.app_context():

        db = get_db()

        row = db.execute(
            """
            SELECT id
            FROM users
            WHERE email=?
            """,
            (email,),
        ).fetchone()

        if row:

            db.execute(
                """
                UPDATE users
                SET
                    role='admin',
                    password_hash=?
                WHERE id=?
                """,
                (
                    generate_password_hash(
                        password
                    ),
                    row["id"],
                ),
            )

        else:

            db.execute(
                """
                INSERT INTO users(
                    email,
                    password_hash,
                    display_name,
                    onboarding_done,
                    role
                )
                VALUES(
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    email,
                    generate_password_hash(
                        password
                    ),
                    "Admin",
                    1,
                    "admin",
                ),
            )

        db.commit()


ensure_admin()


@app.get("/")
def index():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    db = get_db()

    user = db.execute(
        """
        SELECT
            id,
            email,
            display_name,
            onboarding_done
        FROM users
        WHERE id=?
        """,
        (
            session["user_id"],
        ),
    ).fetchone()

    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )

    if not user[
        "onboarding_done"
    ]:

        return redirect(
            url_for(
                "onboarding"
            )
        )

    profile = db.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id=?
        """,
        (
            user["id"],
        ),
    ).fetchone()

    return render_template(
        "index.html",
        user=user,
        profile=profile,
    )


@app.route(
    "/login",
    methods=[
        "GET",
        "POST",
    ],
)
def login():

    error = None

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = (
            request.form.get(
                "password",
                "",
            )
        )

        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE email=?
            """,
            (
                email,
            ),
        ).fetchone()

        if (
            not user
            or not check_password_hash(
                user["password_hash"],
                password,
            )
        ):

            error = (
                "Email hoặc mật khẩu "
                "chưa đúng."
            )

        else:

            session.clear()

            session[
                "user_id"
            ] = user[
                "id"
            ]

            return redirect(
                url_for(
                    "index"
                )
            )

    return render_template(
        "login.html",
        error=error,
    )


@app.route(
    "/register",
    methods=[
        "GET",
        "POST",
    ],
)
def register():

    error = None

    if request.method == "POST":

        name = (
            request.form.get(
                "name",
                "",
            ).strip()
        )

        email = (
            request.form.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = (
            request.form.get(
                "password",
                "",
            )
        )

        if (
            not name
            or not email
            or len(
                password
            ) < 6
        ):

            error = (
                "Điền đủ tên, email "
                "và mật khẩu tối thiểu "
                "6 ký tự."
            )

        else:

            db = get_db()

            try:

                cur = db.execute(
                    """
                    INSERT INTO users(
                        email,
                        password_hash,
                        display_name
                    )
                    VALUES(
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        email,
                        generate_password_hash(
                            password
                        ),
                        name,
                    ),
                )

                db.commit()

                session[
                    "user_id"
                ] = cur.lastrowid

                return redirect(
                    url_for(
                        "onboarding"
                    )
                )

            except Exception:

                error = (
                    "Email này đã "
                    "được đăng ký."
                )

    return render_template(
        "register.html",
        error=error,
    )


@app.route(
    "/onboarding",
    methods=[
        "GET",
        "POST",
    ],
)
def onboarding():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if request.method == "POST":

        d = request.form

        db = get_db()

        db.execute(
            """
            INSERT INTO profiles(
                user_id,
                age,
                occupation,
                industry,
                english_level,
                goals,
                situations,
                preferred_accent
            )
            VALUES(
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )

            ON CONFLICT(user_id)
            DO UPDATE SET

                age=
                    excluded.age,

                occupation=
                    excluded.occupation,

                industry=
                    excluded.industry,

                english_level=
                    excluded.english_level,

                goals=
                    excluded.goals,

                situations=
                    excluded.situations,

                preferred_accent=
                    excluded.preferred_accent
            """,
            (
                session[
                    "user_id"
                ],

                d.get(
                    "age"
                )
                or None,

                d.get(
                    "occupation"
                ),

                d.get(
                    "industry"
                ),

                d.get(
                    "english_level"
                ),

                d.get(
                    "goals"
                ),

                d.get(
                    "situations"
                ),

                d.get(
                    "preferred_accent",
                    "en-US",
                ),
            ),
        )

        db.execute(
            """
            UPDATE users
            SET onboarding_done=1
            WHERE id=?
            """,
            (
                session[
                    "user_id"
                ],
            ),
        )

        db.commit()

        return redirect(
            url_for(
                "index"
            )
        )

    return render_template(
        "onboarding.html"
    )


@app.route(
    "/settings",
    methods=["GET", "POST"],
)
def settings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    user = db.execute(
        "SELECT id, onboarding_done FROM users WHERE id=?",
        (session["user_id"],),
    ).fetchone()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    if not user["onboarding_done"]:
        return redirect(url_for("onboarding"))

    saved = False

    if request.method == "POST":
        d = request.form

        db.execute(
            """
            INSERT INTO profiles(
                user_id, age, occupation, industry, english_level,
                goals, situations, preferred_accent
            )
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                age=excluded.age,
                occupation=excluded.occupation,
                industry=excluded.industry,
                english_level=excluded.english_level,
                goals=excluded.goals,
                situations=excluded.situations,
                preferred_accent=excluded.preferred_accent
            """,
            (
                session["user_id"],
                d.get("age") or None,
                d.get("occupation"),
                d.get("industry"),
                d.get("english_level"),
                d.get("goals"),
                d.get("situations"),
                d.get("preferred_accent", "en-US"),
            ),
        )
        db.commit()
        saved = True

    profile = db.execute(
        "SELECT * FROM profiles WHERE user_id=?",
        (session["user_id"],),
    ).fetchone()

    if not profile:
        return redirect(url_for("onboarding"))

    return render_template(
        "settings.html",
        profile=profile,
        saved=saved,
    )


@app.post(
    "/logout"
)
def logout():

    session.clear()

    return redirect(
        url_for(
            "login"
        )
    )


@app.get(
    "/api/home"
)
def api_home():

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    return jsonify(
        get_home_payload(
            session[
                "user_id"
            ]
        )
    )


@app.get(
    "/api/ai/status"
)
def api_ai_status():

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    return jsonify({
        "configured":
            is_configured(),

        "model":
            model_name(),

        "image_model":
            image_model_name(),

        "vision_model":
            vision_model_name(),

        "visual_threshold":
            visual_threshold(),
    })


@app.get(
    "/api/lesson/<int:lesson_id>"
)
def api_lesson(
    lesson_id,
):

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    lesson = get_lesson_by_id(
        lesson_id,
        session[
            "user_id"
        ],
    )

    if lesson:

        return jsonify(
            lesson
        ), 200

    return jsonify({
        "error":
            "not found"
    }), 404


@app.post(
    "/api/lessons"
)
def api_create_lesson():

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    text = (
        data.get(
            "sentence",
            "",
        ).strip()
    )

    if not text:

        return jsonify({
            "error":
                "Sentence is required"
        }), 400

    if len(
        text
    ) > 500:

        return jsonify({
            "error":
                "Keep one sentence "
                "under 500 characters."
        }), 400

    try:

        result = (
            create_or_get_lesson(
                text,
                session[
                    "user_id"
                ],
            )
        )

        return jsonify(
            result
        )

    except AIServiceError as exc:

        return jsonify({
            "error":
                str(
                    exc
                ),

            "ai_configured":
                is_configured(),
        }), 503


@app.get(
    "/api/lesson/<int:lesson_id>/visual"
)
def api_visual_status(
    lesson_id,
):

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    return jsonify(
        get_visual_status(
            lesson_id
        )
    )


@app.post(
    "/api/lesson/<int:lesson_id>/visual"
)
def api_visual_generate(
    lesson_id,
):

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    try:

        result = (
            create_or_get_visual(
                lesson_id,
                session[
                    "user_id"
                ],
            )
        )

        return jsonify(
            result
        )

    except AIServiceError as exc:

        return jsonify({
            "error":
                str(
                    exc
                )
        }), 503


@app.post(
    "/api/lesson/<int:lesson_id>/complete"
)
def api_complete(
    lesson_id,
):

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    mark_progress(
        session[
            "user_id"
        ],
        lesson_id,
        "learned",
        1.0,
    )

    return jsonify({
        "ok":
            True
    })


@app.post(
    "/api/lesson/<int:lesson_id>/review"
)
def api_review(
    lesson_id,
):

    if "user_id" not in session:

        return jsonify({
            "error":
                "unauthorized"
        }), 401

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    result = data.get(
        "result",
        "remembered",
    )

    record_review(
        session[
            "user_id"
        ],
        lesson_id,
        result,
    )

    return jsonify({
        "ok":
            True
    })


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=[
        "GET",
        "POST",
    ],
)
def admin_login():

    error = None

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = (
            request.form.get(
                "password",
                "",
            )
        )

        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE
                email=?
                AND role='admin'
            """,
            (
                email,
            ),
        ).fetchone()

        if (
            not user
            or not check_password_hash(
                user[
                    "password_hash"
                ],
                password,
            )
        ):

            error = (
                "Admin email hoặc "
                "mật khẩu chưa đúng."
            )

        else:

            session.clear()

            session[
                "admin_id"
            ] = user[
                "id"
            ]

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

    return render_template(
        "admin_login.html",
        error=error,
    )


def _admin_user():

    if "admin_id" not in session:
        return None

    return get_db().execute(
        """
        SELECT
            id,
            email,
            display_name
        FROM users
        WHERE
            id=?
            AND role='admin'
        """,
        (
            session[
                "admin_id"
            ],
        ),
    ).fetchone()


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.get(
    "/admin"
)
def admin_dashboard():

    admin = _admin_user()

    if not admin:

        return redirect(
            url_for(
                "admin_login"
            )
        )

    try:

        days = int(
            request.args.get(
                "days",
                "30",
            )
        )

    except ValueError:

        days = 30

    data = dashboard_payload(
        days
    )

    data[
        "usd_vnd_rate"
    ] = float(
        get_setting(
            "usd_vnd_rate",
            "26000",
        )
    )

    return render_template(
        "admin_dashboard.html",
        admin=admin,
        data=data,
    )


# =========================================================
# ADMIN AI CONFIGURATION
# =========================================================

@app.route(
    "/admin/ai-config",
    methods=[
        "GET",
        "POST",
    ],
)
def admin_ai_config():

    admin = _admin_user()

    if not admin:

        return redirect(
            url_for(
                "admin_login"
            )
        )

    saved = False
    error = None

    if request.method == "POST":

        try:

            save_ai_config(
                request.form
            )

            saved = True

        except Exception as exc:

            error = str(
                exc
            )

    config = get_ai_config()

    return render_template(
        "admin_ai_config.html",
        admin=admin,
        config=config,
        saved=saved,
        error=error,
    )


@app.post(
    "/api/admin/ai-config/test"
)
def api_admin_ai_config_test():

    if not _admin_user():

        return jsonify({
            "error":
                "admin unauthorized"
        }), 401

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:

        result = (
            test_openai_connection(
                api_key=(
                    data.get(
                        "openai_api_key"
                    )
                    or None
                ),

                text_model=(
                    data.get(
                        "openai_model"
                    )
                    or None
                ),

                image_model=(
                    data.get(
                        "openai_image_model"
                    )
                    or None
                ),

                vision_model=(
                    data.get(
                        "openai_vision_model"
                    )
                    or None
                ),
            )
        )

        return jsonify(
            result
        )

    except Exception as exc:

        return jsonify({
            "ok":
                False,

            "error":
                str(
                    exc
                ),
        }), 400


# =========================================================
# ADMIN COST API
# =========================================================

@app.get(
    "/api/admin/costs"
)
def api_admin_costs():

    if not _admin_user():

        return jsonify({
            "error":
                "admin unauthorized"
        }), 401

    try:

        days = int(
            request.args.get(
                "days",
                "30",
            )
        )

    except ValueError:

        days = 30

    data = dashboard_payload(
        days
    )

    data[
        "usd_vnd_rate"
    ] = float(
        get_setting(
            "usd_vnd_rate",
            "26000",
        )
    )

    return jsonify(
        data
    )


@app.post(
    "/admin/logout"
)
def admin_logout():

    session.clear()

    return redirect(
        url_for(
            "admin_login"
        )
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    debug = (
        os.getenv(
            "FLASK_DEBUG",
            "1",
        )
        == "1"
    )

    port = int(
        os.getenv(
            "PORT",
            "5000",
        )
    )

    app.run(
        debug=debug,
        host="0.0.0.0",
        port=port,
    )