# Prep — AI-Powered Interview Coach

Prep is a small Flask application for MCA students to practise interview answers and receive explainable, automated feedback. It combines the existing TF-IDF/cosine-similarity scorer and curated CSV question bank with SQLite persistence, question-management APIs, account registration/login, private practice history, and a responsive dashboard.

> **Scoring is a practice aid, not a perfect measure of understanding.** TF-IDF relies on word and phrase overlap; it does not understand meaning as deeply as a person or a modern language model.

## Features

- Five interview categories: HR / Behavioral, CS Fundamentals, Python Programming, Machine Learning Basics, and System Design.
- Beginner, Intermediate, and Advanced question levels.
- Five-question practice sessions with evaluation, retry, and a session recap.
- Scores for overall answer quality, text similarity, and concept coverage, plus covered/missing concepts and feedback.
- SQLite storage for questions and submitted answers/results; CSV import is repeatable and adds new questions without duplicating existing ones.
- Dashboard with attempt totals, average and best scores, recent score trend, category averages, and saved history.
- JSON REST APIs for question filtering, question CRUD, answer evaluation, and result history.
- Email/password registration and login, Werkzeug password hashing, signed Flask sessions, CSRF protection, and user-scoped result history.

## Setup and run

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m app.app
```

Open [http://127.0.0.1:5050](http://127.0.0.1:5050), create an account, and log in to practise. On first start, Prep creates `data/prep.db` and imports questions from `data/question_bank.csv`. On later starts, newly added CSV questions are imported while existing records and practice history are kept.

For a stable secret across app restarts, set `PREP_SECRET_KEY` to a long random value. For example, macOS/Linux:

```bash
export PREP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

The app generates a temporary random secret automatically for local development when this variable is unset; that invalidates sessions after restart. Set `PREP_COOKIE_SECURE=1` when serving over HTTPS (leave it unset for local HTTP development). Session cookies are HTTP-only and use `SameSite=Lax`.

To extend the source question bank, edit `data/build_question_bank.py`, then regenerate the CSV and restart the application:

```bash
python data/build_question_bank.py
```

The generator assigns question difficulties within each category and writes the CSV beside itself. You can also use the question CRUD API to manage database records directly. SQLite files are ignored by Git.

## Practice API

All endpoints return JSON except successful question deletion (`204 No Content`). Validation errors return `400`, missing records `404`, and questions that have saved practice history cannot be deleted (`409`).

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/categories` | List supported categories and difficulties |
| `GET` | `/api/questions?category=Python%20Programming&difficulty=Beginner` | List/filter questions (reference answers are not exposed) |
| `POST` | `/api/questions` | Create a question |
| `GET` | `/api/questions/<id>` | View a question including its reference answer and key points |
| `PUT` | `/api/questions/<id>` | Replace/update question fields |
| `DELETE` | `/api/questions/<id>` | Delete a question without saved results |
| `POST` | `/api/answers` | Evaluate and persist an answer |
| `GET` | `/api/results?limit=20&session_id=<id>` | Retrieve saved results |
| `GET` | `/api/results/summary` | Dashboard metrics and chart data |
| `GET` | `/api/results/<id>` | Retrieve one saved result |

Example answer submission:

```json
{
  "question_id": 1,
  "answer": "A stack follows last-in, first-out order...",
  "session_id": "a-practice-session"
}
```

`session_id` is optional; if omitted, the API creates one. Question creation/update JSON uses `category`, `difficulty`, `question`, `model_answer`, and comma-separated `key_points`. The original `/get_question` and `/score_answer` POST routes remain available for compatibility. A logged-in browser session is required for answers, CRUD writes, dashboard data, and saved results; mutating API requests must include the CSRF token in the `X-CSRFToken` header.

Saved attempts include their owning user ID. Result-list, summary, and individual-result queries are scoped to the logged-in account; a result belonging to another user is not returned. The database initialization adds `user_id` to an older results table without deleting saved rows; legacy attempts remain unassigned and are not shown as belonging to any account. Question bank reads are public, while question CRUD writes require login. This remains a local academic demonstration; question management is available to every registered user and is not a role-based admin console.

## Architecture

```text
app/
  app.py                 Flask routes, JSON validation, application factory
  database.py            SQLite users/questions/results, CSV import, serialization
  templates/             Public home, registration, login, and practice/dashboard pages
  static/                Responsive styles, password toggle, practice/dashboard scripts
model/
  answer_scorer.py       TF-IDF, cosine similarity, concept coverage, feedback
data/
  question_bank.csv      Human-curated source question bank
  build_question_bank.py CSV generator and difficulty assignment
tests/
  test_app.py            Scorer, API, persistence, and CRUD tests
```

Flask reads questions from SQLite. During startup, the CSV importer adds records that are not already present, keeping the CSV easy to edit while allowing CRUD-managed questions and saved attempts to live in the database. The database has three simple tables: `users`, `questions`, and `practice_results`.

## Scoring algorithm (viva explanation)

For each non-empty candidate answer:

1. **Text similarity:** Fit a TF-IDF vectorizer (English stop-word removal, unigrams and bigrams) to the candidate and curated reference answer. Cosine similarity is converted to a 0–100 score.
2. **Concept coverage:** Tokenize each comma-separated key concept and the candidate answer. A concept is covered when at least half of its significant terms appear as whole tokens. Coverage is covered concepts divided by total concepts, expressed as a percentage.
3. **Effort multiplier:** Answers under 8 words receive a `0.5` multiplier; answers of 8–14 words receive `0.8`; answers of 15 or more words receive `1.0`.
4. **Final score:** `round((0.55 × text_similarity + 0.45 × concept_coverage) × effort_multiplier)`, bounded to 0–100.

Weights can be changed with `PREP_SIMILARITY_WEIGHT` and `PREP_COVERAGE_WEIGHT`. They are normalized to sum to 1, so for example `0.6` and `0.4` produce a 60/40 blend. A zero or invalid weight pair is rejected. Missing concepts are also returned individually to make the score actionable.

**Limitation to explain during evaluation:** This is an interpretable lexical baseline, not perfect semantic understanding. Synonyms or a valid answer with different wording may be under-scored; keyword matches can also miss context. The curated reference answers and concept lists are therefore part of the model's assumptions.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary SQLite databases and cover user creation, password hashing, login/logout, CSRF validation, duplicate emails, route protection, question APIs, and results isolation between accounts.
