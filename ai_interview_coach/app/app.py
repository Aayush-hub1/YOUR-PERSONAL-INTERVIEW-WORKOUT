"""Flask application and REST API for Prep — AI Interview Coach."""

import os
import re
import secrets
import sqlite3
import sys
import uuid
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import (  # noqa: E402
    CATEGORIES,
    DEFAULT_DATABASE,
    DIFFICULTIES,
    close_db,
    get_db,
    init_db,
    list_results,
    question_dict,
    result_dict,
)
from model.answer_scorer import (  # noqa: E402
    DEFAULT_COVERAGE_WEIGHT,
    DEFAULT_SIMILARITY_WEIGHT,
    score_answer,
)

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def is_valid_email(email):
    if not EMAIL_PATTERN.fullmatch(email):
        return False
    local_part = email.rsplit("@", 1)[0]
    return not local_part.startswith(".") and not local_part.endswith(".") and ".." not in local_part


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Authentication is required."), 401
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def _json_body():
    if not request.is_json:
        return None
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _question_payload(data, existing=None):
    merged = dict(existing or {})
    merged.update(data)
    required = ("category", "difficulty", "question", "model_answer", "key_points")
    if any(not isinstance(merged.get(field), str) or not merged[field].strip() for field in required):
        return None, "category, difficulty, question, model_answer, and key_points are required."
    for field, limit in (("question", 500), ("model_answer", 5000), ("key_points", 1000)):
        if len(merged[field].strip()) > limit:
            return None, f"{field} must be {limit} characters or fewer."
    normalized = {field: merged[field].strip() for field in required}
    if normalized["category"] not in CATEGORIES:
        return None, "Choose one of the supported interview categories."
    if normalized["difficulty"] not in DIFFICULTIES:
        return None, "difficulty must be Beginner, Intermediate, or Advanced."
    return normalized, None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=str(DEFAULT_DATABASE),
        SECRET_KEY=os.environ.get("PREP_SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("PREP_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        SIMILARITY_WEIGHT=float(os.environ.get("PREP_SIMILARITY_WEIGHT", DEFAULT_SIMILARITY_WEIGHT)),
        COVERAGE_WEIGHT=float(os.environ.get("PREP_COVERAGE_WEIGHT", DEFAULT_COVERAGE_WEIGHT)),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    csrf = CSRFProtect()
    csrf.init_app(app)
    app.teardown_appcontext(close_db)
    with app.app_context():
        imported_count = init_db()
    if imported_count:
        app.logger.info("Imported %s questions from the CSV question bank.", imported_count)

    @app.before_request
    def load_current_user():
        user_id = session.get("user_id")
        g.current_user = None
        if isinstance(user_id, int) and not isinstance(user_id, bool):
            g.current_user = get_db().execute(
                "SELECT id, full_name, email, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if g.current_user is None:
                session.clear()

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error="CSRF validation failed. Refresh the page and try again."), 400
        flash("Your form session expired. Please try again.", "danger")
        if request.path == "/logout" and g.current_user is not None:
            return redirect(url_for("dashboard"))
        template = "register.html" if request.path == "/register" else "login.html"
        return render_template(template), 400

    @app.route("/")
    def home():
        if g.current_user is not None:
            return redirect(url_for("dashboard"))
        return render_template("home.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.current_user is not None:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            errors = []
            if not full_name:
                errors.append("Full name is required.")
            elif len(full_name) > 100:
                errors.append("Full name must be 100 characters or fewer.")
            if not email:
                errors.append("Email address is required.")
            elif len(email) > 254 or not is_valid_email(email):
                errors.append("Enter a valid email address.")
            if not password:
                errors.append("Password is required.")
            elif len(password) < 8:
                errors.append("Password must be at least 8 characters long.")
            elif len(password) > 128:
                errors.append("Password must be 128 characters or fewer.")
            if password != confirm_password:
                errors.append("Passwords do not match.")

            if not errors:
                db = get_db()
                try:
                    db.execute(
                        "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                        (full_name, email, generate_password_hash(password)),
                    )
                    db.commit()
                except sqlite3.IntegrityError as error:
                    db.rollback()
                    if "users.email" in str(error).lower() or "unique constraint failed: users.email" in str(error).lower():
                        errors.append("An account with that email already exists.")
                    else:
                        raise
                else:
                    flash("Your account was created. Please log in.", "success")
                    return redirect(url_for("login"))

            for error in errors:
                flash(error, "danger")
            return render_template("register.html", full_name=full_name, email=email), 400
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.current_user is not None:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = None
            if email and password and len(email) <= 254:
                user = get_db().execute(
                    "SELECT id, email, password_hash FROM users WHERE email = ?",
                    (email,),
                ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Invalid email or password.", "danger")
                return render_template("login.html", email=email), 401

            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            requested_next = request.args.get("next", "")
            parsed_next = urlparse(requested_next)
            if (
                requested_next.startswith("/")
                and not requested_next.startswith("//")
                and "\\" not in requested_next
                and not parsed_next.scheme
                and not parsed_next.netloc
            ):
                return redirect(requested_next)
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("home"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template(
            "index.html",
            categories=CATEGORIES,
            difficulties=DIFFICULTIES,
            current_user=g.current_user,
        )

    @app.get("/api/categories")
    def get_categories():
        return jsonify({"categories": CATEGORIES, "difficulties": DIFFICULTIES})

    @app.get("/api/questions")
    def get_questions():
        category = request.args.get("category")
        difficulty = request.args.get("difficulty")
        if category and category not in CATEGORIES:
            return jsonify(error="Unsupported category."), 400
        if difficulty and difficulty not in DIFFICULTIES:
            return jsonify(error="Unsupported difficulty."), 400

        query = "SELECT * FROM questions WHERE 1 = 1"
        parameters = []
        if category:
            query += " AND category = ?"
            parameters.append(category)
        if difficulty:
            query += " AND difficulty = ?"
            parameters.append(difficulty)
        query += " ORDER BY id"
        rows = get_db().execute(query, parameters).fetchall()
        return jsonify({"questions": [question_dict(row) for row in rows]})

    @app.post("/api/questions")
    @login_required
    def create_question():
        data = _json_body()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        values, error = _question_payload(data)
        if error:
            return jsonify(error=error), 400
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO questions (category, difficulty, question, model_answer, key_points)
            VALUES (:category, :difficulty, :question, :model_answer, :key_points)
            """,
            values,
        )
        db.commit()
        row = db.execute("SELECT * FROM questions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"question": question_dict(row, include_reference=True)}), 201

    @app.get("/api/questions/<int:question_id>")
    def get_question(question_id):
        row = get_db().execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify(error="Question not found."), 404
        return jsonify({"question": question_dict(row, include_reference=True)})

    @app.put("/api/questions/<int:question_id>")
    @login_required
    def update_question(question_id):
        db = get_db()
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify(error="Question not found."), 404
        data = _json_body()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        current = {field: row[field] for field in ("category", "difficulty", "question", "model_answer", "key_points")}
        values, error = _question_payload(data, current)
        if error:
            return jsonify(error=error), 400
        db.execute(
            """
            UPDATE questions
            SET category = :category, difficulty = :difficulty, question = :question,
                model_answer = :model_answer, key_points = :key_points
            WHERE id = :id
            """,
            {**values, "id": question_id},
        )
        db.commit()
        updated = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return jsonify({"question": question_dict(updated, include_reference=True)})

    @app.delete("/api/questions/<int:question_id>")
    @login_required
    def delete_question(question_id):
        db = get_db()
        try:
            cursor = db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
            if cursor.rowcount == 0:
                return jsonify(error="Question not found."), 404
            db.commit()
        except sqlite3.IntegrityError as error:
            db.rollback()
            if "FOREIGN KEY constraint failed" in str(error):
                return jsonify(error="This question has saved practice results and cannot be deleted."), 409
            raise
        return "", 204

    @app.post("/api/answers")
    @login_required
    def submit_answer():
        data = _json_body()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        question_id = data.get("question_id")
        answer = data.get("answer")
        if isinstance(question_id, bool) or not isinstance(question_id, int) or question_id < 1:
            return jsonify(error="question_id must be a positive integer."), 400
        if not isinstance(answer, str) or not answer.strip():
            return jsonify(error="answer must not be empty."), 400
        if len(answer) > 10000:
            return jsonify(error="answer must be 10000 characters or fewer."), 400
        session_id = data.get("session_id") or str(uuid.uuid4())
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 80:
            return jsonify(error="session_id must be a non-empty string of at most 80 characters."), 400

        db = get_db()
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify(error="Question not found."), 404
        result = score_answer(
            answer.strip(),
            row["model_answer"],
            row["key_points"],
            similarity_weight=app.config["SIMILARITY_WEIGHT"],
            coverage_weight=app.config["COVERAGE_WEIGHT"],
        )
        cursor = db.execute(
            """
            INSERT INTO practice_results
                (user_id, session_id, question_id, answer, similarity_score, keyword_score,
                 final_score, covered_points, missing_points, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g.current_user["id"],
                session_id.strip(),
                question_id,
                answer.strip(),
                result["similarity_score"],
                result["keyword_score"],
                result["final_score"],
                "\n".join(result["covered_points"]),
                "\n".join(result["missing_points"]),
                "\n".join(result["feedback"]),
            ),
        )
        db.commit()
        return jsonify(
            {
                "result": {
                    **result,
                    "id": cursor.lastrowid,
                    "session_id": session_id.strip(),
                    "question": row["question"],
                    "category": row["category"],
                    "difficulty": row["difficulty"],
                    "model_answer": row["model_answer"],
                }
            }
        ), 201

    @app.get("/api/results")
    @login_required
    def get_results():
        session_id = request.args.get("session_id")
        try:
            limit = int(request.args.get("limit", 20))
        except ValueError:
            return jsonify(error="limit must be an integer between 1 and 100."), 400
        if not 1 <= limit <= 100:
            return jsonify(error="limit must be an integer between 1 and 100."), 400
        return jsonify({"results": list_results(user_id=g.current_user["id"], limit=limit, session_id=session_id)})

    @app.get("/api/results/summary")
    @login_required
    def get_results_summary():
        db = get_db()
        totals = db.execute(
            "SELECT COUNT(*) AS attempts, COALESCE(ROUND(AVG(final_score)), 0) AS average_score, "
            "COALESCE(MAX(final_score), 0) AS best_score FROM practice_results WHERE user_id = ?",
            (g.current_user["id"],),
        ).fetchone()
        by_category = db.execute(
            """
            SELECT q.category, COUNT(*) AS attempts, ROUND(AVG(r.final_score)) AS average_score
            FROM practice_results r JOIN questions q ON q.id = r.question_id
            WHERE r.user_id = ?
            GROUP BY q.category ORDER BY q.category
            """,
            (g.current_user["id"],),
        ).fetchall()
        recent = list(reversed(list_results(user_id=g.current_user["id"], limit=10)))
        return jsonify(
            {
                "attempts": totals["attempts"],
                "average_score": totals["average_score"],
                "best_score": totals["best_score"],
                "category_stats": [dict(row) for row in by_category],
                "score_trend": [
                    {"date": row["created_at"], "score": row["final_score"], "question": row["question"]}
                    for row in recent
                ],
            }
        )

    @app.get("/api/results/<int:result_id>")
    @login_required
    def get_result(result_id):
        row = get_db().execute(
            """
            SELECT r.*, q.category, q.difficulty, q.question
            FROM practice_results r JOIN questions q ON q.id = r.question_id
            WHERE r.id = ? AND r.user_id = ?
            """,
            (result_id, g.current_user["id"]),
        ).fetchone()
        if row is None:
            return jsonify(error="Practice result not found."), 404
        return jsonify({"result": result_dict(row)})

    # Keep the original browser/API routes working for existing integrations.
    @app.post("/get_question")
    @login_required
    def legacy_get_question():
        data = _json_body()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        category = data.get("category")
        difficulty = data.get("difficulty")
        if category not in CATEGORIES or (difficulty and difficulty not in DIFFICULTIES):
            return jsonify(error="Unsupported category or difficulty."), 400
        query = "SELECT id, category, question FROM questions WHERE category = ?"
        parameters = [category]
        if difficulty:
            query += " AND difficulty = ?"
            parameters.append(difficulty)
        query += " ORDER BY RANDOM() LIMIT 1"
        row = get_db().execute(query, parameters).fetchone()
        if row is None:
            return jsonify(error="No questions found for this category and difficulty."), 404
        return jsonify({"question_id": row["id"], "question": row["question"], "category": row["category"]})

    @app.post("/score_answer")
    @login_required
    def legacy_score_answer():
        data = _json_body()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        question_id = data.get("question_id")
        if isinstance(question_id, bool) or not isinstance(question_id, int):
            return jsonify(error="Invalid question reference."), 400
        row = get_db().execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify(error="Invalid question reference."), 400
        answer = data.get("answer")
        if not isinstance(answer, str):
            return jsonify(error="answer must be a string."), 400
        result = score_answer(
            answer,
            row["model_answer"],
            row["key_points"],
            similarity_weight=app.config["SIMILARITY_WEIGHT"],
            coverage_weight=app.config["COVERAGE_WEIGHT"],
        )
        return jsonify({**result, "model_answer": row["model_answer"]})

    return app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="127.0.0.1", port=5050)
