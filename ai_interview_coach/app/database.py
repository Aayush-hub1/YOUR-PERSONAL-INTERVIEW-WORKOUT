"""Small SQLite persistence layer for questions and practice attempts."""

import csv
import sqlite3
from pathlib import Path

from flask import current_app, g

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "prep.db"
QUESTION_BANK = PROJECT_ROOT / "data" / "question_bank.csv"
CATEGORIES = (
    "HR / Behavioral",
    "CS Fundamentals",
    "Python Programming",
    "Machine Learning Basics",
    "System Design",
)
DIFFICULTIES = ("Beginner", "Intermediate", "Advanced")


def get_db():
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def import_questions_from_csv(csv_path=QUESTION_BANK):
    """Import new CSV questions without duplicating or replacing saved records."""
    db = get_db()
    category_positions = {}
    imported = 0
    with Path(csv_path).open(newline="", encoding="utf-8") as bank_file:
        for row in csv.DictReader(bank_file):
            category = (row.get("category") or "").strip()
            position = category_positions.get(category, 0)
            category_positions[category] = position + 1
            difficulty = (row.get("difficulty") or "").strip()
            if difficulty not in DIFFICULTIES:
                difficulty = ("Beginner", "Intermediate", "Advanced")[min(position, 2)]
            question = (row.get("question") or "").strip()
            exists = db.execute(
                "SELECT 1 FROM questions WHERE category = ? AND question = ?",
                (category, question),
            ).fetchone()
            if exists:
                continue
            db.execute(
                """
                INSERT INTO questions (category, difficulty, question, model_answer, key_points)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    category,
                    difficulty,
                    question,
                    (row.get("model_answer") or "").strip(),
                    (row.get("key_points") or "").strip(),
                ),
            )
            imported += 1
    db.commit()
    return imported


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('Beginner', 'Intermediate', 'Advanced')),
            question TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            key_points TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS practice_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            answer TEXT NOT NULL,
            similarity_score INTEGER NOT NULL,
            keyword_score INTEGER NOT NULL,
            final_score INTEGER NOT NULL,
            covered_points TEXT NOT NULL,
            missing_points TEXT NOT NULL,
            feedback TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_results_session ON practice_results(session_id);
        CREATE INDEX IF NOT EXISTS idx_results_created ON practice_results(created_at);
        """
    )
    result_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(practice_results)").fetchall()
    }
    if "user_id" not in result_columns:
        db.execute("ALTER TABLE practice_results ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
    db.execute("CREATE INDEX IF NOT EXISTS idx_results_user ON practice_results(user_id, id)")
    db.commit()
    return import_questions_from_csv()


def question_dict(row, include_reference=False):
    result = {
        "id": row["id"],
        "category": row["category"],
        "difficulty": row["difficulty"],
        "question": row["question"],
    }
    if include_reference:
        result.update(model_answer=row["model_answer"], key_points=row["key_points"])
    return result


def result_dict(row):
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "question_id": row["question_id"],
        "category": row["category"],
        "difficulty": row["difficulty"],
        "question": row["question"],
        "answer": row["answer"],
        "similarity_score": row["similarity_score"],
        "keyword_score": row["keyword_score"],
        "final_score": row["final_score"],
        "covered_points": row["covered_points"].split("\n") if row["covered_points"] else [],
        "missing_points": row["missing_points"].split("\n") if row["missing_points"] else [],
        "feedback": row["feedback"].split("\n") if row["feedback"] else [],
        "created_at": row["created_at"],
    }


def list_results(user_id, limit=20, session_id=None):
    db = get_db()
    query = """
        SELECT r.*, q.category, q.difficulty, q.question
        FROM practice_results r
        JOIN questions q ON q.id = r.question_id
        WHERE r.user_id = ?
    """
    params = [user_id]
    if session_id:
        query += " AND r.session_id = ?"
        params.append(session_id)
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(limit)
    return [result_dict(row) for row in db.execute(query, params).fetchall()]
