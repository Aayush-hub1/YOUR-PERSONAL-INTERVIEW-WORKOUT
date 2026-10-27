import sqlite3
import tempfile
import unittest
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

from app.app import create_app
from model.answer_scorer import score_answer
from werkzeug.security import check_password_hash


class TokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("name") == "csrf_token":
            self.token = values.get("value")
        elif tag == "meta" and values.get("name") == "csrf-token":
            self.token = values.get("content")


def csrf_token(client, path):
    response = client.get(path)
    parser = TokenParser()
    parser.feed(response.get_data(as_text=True))
    if not parser.token:
        raise AssertionError(f"No CSRF token found on {path}.")
    return parser.token


class AnswerScorerTests(unittest.TestCase):
    def test_empty_answer_has_zero_score_and_all_concepts_missing(self):
        result = score_answer("", "A reference answer", "first concept, second concept")
        self.assertEqual(result["final_score"], 0)
        self.assertEqual(result["missing_points"], ["first concept", "second concept"])
        self.assertIn("No answer provided.", result["feedback"])

    def test_scoring_reports_covered_and_missing_concepts(self):
        result = score_answer(
            "A stack is LIFO and removes the newest item first, unlike a queue.",
            "A stack follows LIFO while a queue follows FIFO. The insertion and removal order differs.",
            "LIFO, FIFO, insertion order, removal order",
        )
        self.assertIn("lifo", result["covered_points"])
        self.assertIn("fifo", result["missing_points"])
        self.assertGreaterEqual(result["final_score"], 0)
        self.assertLessEqual(result["final_score"], 100)

    def test_weights_are_configurable_and_validated(self):
        weighted = score_answer(
            "A useful answer with enough words to explain the central idea clearly.",
            "A useful answer",
            "central idea",
            1,
            0,
        )
        self.assertEqual(
            weighted["final_score"],
            round(weighted["similarity_score"] * weighted["length_penalty"]),
        )
        with self.assertRaises(ValueError):
            score_answer("answer", "answer", "answer", 0, 0)


class AuthAndDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": self.db_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register(self, client=None, full_name="Prep Student", email="student@example.com", password="secure-pass-123"):
        client = client or self.client
        token = csrf_token(client, "/register")
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": full_name,
                "email": email,
                "password": password,
                "confirm_password": password,
            },
        )
        return response

    def login(self, client=None, email="student@example.com", password="secure-pass-123"):
        client = client or self.client
        token = csrf_token(client, "/login")
        response = client.post(
            "/login",
            data={"csrf_token": token, "email": email, "password": password},
            follow_redirects=True,
        )
        parser = TokenParser()
        parser.feed(response.get_data(as_text=True))
        return response, parser.token

    def make_account(self, email, full_name):
        client = self.app.test_client()
        registration = self.register(client, full_name=full_name, email=email)
        self.assertEqual(registration.status_code, 302)
        login_response, token = self.login(client, email=email)
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(token)
        return client, token

    def test_registration_hashes_password_and_normalizes_email(self):
        response = self.register(email="  STUDENT@Example.com ")
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.db_path)) as db:
            user = db.execute("SELECT full_name, email, password_hash, created_at FROM users").fetchone()
        self.assertEqual(user[0], "Prep Student")
        self.assertEqual(user[1], "student@example.com")
        self.assertNotEqual(user[2], "secure-pass-123")
        self.assertTrue(check_password_hash(user[2], "secure-pass-123"))
        self.assertTrue(user[3])

    def test_registration_validates_required_fields_email_password_and_confirmation(self):
        cases = [
            ({"full_name": "", "email": "student@example.com", "password": "secure-pass-123", "confirm_password": "secure-pass-123"}, "Full name is required."),
            ({"full_name": "Student", "email": "not-an-email", "password": "secure-pass-123", "confirm_password": "secure-pass-123"}, "Enter a valid email address."),
            ({"full_name": "Student", "email": "student@example.com", "password": "short", "confirm_password": "short"}, "at least 8 characters"),
            ({"full_name": "Student", "email": "student@example.com", "password": "secure-pass-123", "confirm_password": "different-pass"}, "Passwords do not match."),
        ]
        for fields, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                token = csrf_token(self.client, "/register")
                response = self.client.post("/register", data={**fields, "csrf_token": token})
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected_message, response.get_data(as_text=True))

    def test_duplicate_email_registration_is_rejected_case_insensitively(self):
        self.assertEqual(self.register(email="student@example.com").status_code, 302)
        duplicate = self.register(email="STUDENT@example.com")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already exists", duplicate.get_data(as_text=True))
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)

    def test_login_rejects_invalid_credentials_and_success_creates_session(self):
        self.register()
        bad_login_token = csrf_token(self.client, "/login")
        invalid = self.client.post(
            "/login",
            data={"csrf_token": bad_login_token, "email": "student@example.com", "password": "wrong-password"},
        )
        self.assertEqual(invalid.status_code, 401)
        self.assertIn("Invalid email or password", invalid.get_data(as_text=True))

        response, token = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard", response.request.path)
        self.assertTrue(token)

    def test_dashboard_and_private_apis_require_login_and_logout_clears_session(self):
        unauthenticated = self.client.get("/dashboard")
        self.assertEqual(unauthenticated.status_code, 302)
        self.assertIn("/login", unauthenticated.location)
        self.assertEqual(self.client.get("/api/results").status_code, 401)
        self.assertEqual(self.client.get("/api/results/summary").status_code, 401)
        token = csrf_token(self.client, "/login")
        self.assertEqual(
            self.client.post(
                "/api/answers",
                json={"question_id": 1, "answer": "An answer"},
                headers={"X-CSRFToken": token},
            ).status_code,
            401,
        )
        self.register()
        response, _token = self.login()
        self.assertEqual(response.status_code, 200)

        logout_token = csrf_token(self.client, "/dashboard")
        logged_out = self.client.post("/logout", data={"csrf_token": logout_token})
        self.assertEqual(logged_out.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_csrf_protection_rejects_missing_token(self):
        response = self.client.post(
            "/register",
            data={
                "full_name": "Student",
                "email": "student@example.com",
                "password": "secure-pass-123",
                "confirm_password": "secure-pass-123",
            },
        )
        self.assertEqual(response.status_code, 400)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)

    def test_questions_api_and_answer_history_are_scoped_to_logged_in_user(self):
        first_client, first_token = self.make_account("first@example.com", "First Student")
        second_client, second_token = self.make_account("second@example.com", "Second Student")
        question_response = first_client.get(
            "/api/questions?category=Python%20Programming&difficulty=Beginner"
        )
        self.assertEqual(question_response.status_code, 200)
        question = question_response.get_json()["questions"][0]

        answer_data = {
            "question_id": question["id"],
            "answer": "A list is mutable and can change, while a tuple is immutable and suits fixed values.",
            "session_id": "shared-session-id",
        }
        first_result = first_client.post(
            "/api/answers",
            json=answer_data,
            headers={"X-CSRFToken": first_token},
        )
        second_result = second_client.post(
            "/api/answers",
            json=answer_data,
            headers={"X-CSRFToken": second_token},
        )
        self.assertEqual(first_result.status_code, 201)
        self.assertEqual(second_result.status_code, 201)
        first_result_id = first_result.get_json()["result"]["id"]

        first_history = first_client.get("/api/results?session_id=shared-session-id").get_json()["results"]
        second_history = second_client.get("/api/results?session_id=shared-session-id").get_json()["results"]
        self.assertEqual(len(first_history), 1)
        self.assertEqual(len(second_history), 1)
        self.assertNotEqual(first_history[0]["id"], second_history[0]["id"])
        self.assertEqual(second_client.get(f"/api/results/{first_result_id}").status_code, 404)
        self.assertEqual(first_client.get(f"/api/results/{first_result_id}").status_code, 200)
        self.assertEqual(first_client.get("/api/results/summary").get_json()["attempts"], 1)

    def test_question_crud_requires_login_and_csrf(self):
        anonymous_token = csrf_token(self.client, "/login")
        self.assertEqual(
            self.client.post(
                "/api/questions",
                json={},
                headers={"X-CSRFToken": anonymous_token},
            ).status_code,
            401,
        )
        self.register()
        self.login()
        token = csrf_token(self.client, "/dashboard")
        payload = {
            "category": "Python Programming",
            "difficulty": "Advanced",
            "question": "How does a context manager work?",
            "model_answer": "It manages setup and cleanup around a block of code.",
            "key_points": "enter, exit, cleanup",
        }
        created = self.client.post("/api/questions", json=payload, headers={"X-CSRFToken": token})
        self.assertEqual(created.status_code, 201)
        question_id = created.get_json()["question"]["id"]
        payload["question"] = "Explain a context manager."
        updated = self.client.put(
            f"/api/questions/{question_id}",
            json=payload,
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(updated.get_json()["question"]["question"], payload["question"])
        deleted = self.client.delete(f"/api/questions/{question_id}", headers={"X-CSRFToken": token})
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(f"/api/questions/{question_id}").status_code, 404)

    def test_api_rejects_invalid_payloads(self):
        self.register()
        _response, token = self.login()
        self.assertEqual(
            self.client.post("/api/answers", json={}, headers={"X-CSRFToken": token}).status_code,
            400,
        )
        self.assertEqual(self.client.get("/api/questions?difficulty=Expert").status_code, 400)
        self.assertEqual(self.client.get("/api/results?limit=1000").status_code, 400)

    def test_existing_database_is_migrated_without_deleting_old_attempts(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.db")
        with closing(sqlite3.connect(legacy_path)) as db:
            db.executescript(
                """
                CREATE TABLE questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    question TEXT NOT NULL,
                    model_answer TEXT NOT NULL,
                    key_points TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO questions (category, difficulty, question, model_answer, key_points)
                VALUES ('HR / Behavioral', 'Beginner', 'Legacy question?', 'Reference.', 'legacy concept');
                CREATE TABLE practice_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question_id INTEGER NOT NULL,
                    answer TEXT NOT NULL,
                    similarity_score INTEGER NOT NULL,
                    keyword_score INTEGER NOT NULL,
                    final_score INTEGER NOT NULL,
                    covered_points TEXT NOT NULL,
                    missing_points TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO practice_results
                    (session_id, question_id, answer, similarity_score, keyword_score,
                     final_score, covered_points, missing_points, feedback)
                VALUES ('legacy-session', 1, 'Old attempt', 20, 30, 25, '', 'legacy concept', 'Old result');
                """
            )

        legacy_app = create_app(
            {"TESTING": True, "SECRET_KEY": "migration-test-key", "DATABASE": legacy_path}
        )
        legacy_client = legacy_app.test_client()
        self.assertEqual(self.register(legacy_client, email="migrated@example.com").status_code, 302)
        self.login(legacy_client, email="migrated@example.com")
        self.assertEqual(legacy_client.get("/api/results").get_json()["results"], [])
        with closing(sqlite3.connect(legacy_path)) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(practice_results)")}
            self.assertIn("user_id", columns)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM practice_results").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
