# Prep — AI-Powered Interview Coach

## Mini-Project Report

**Programme:** Master of Computer Applications (MCA)  
**Specialization:** Artificial Intelligence and Machine Learning  
**Project type:** Academic mini project  
**Prepared:** 26 October 2026  
**Student:** ______________________________  
**Institution:** ___________________________

---

## Abstract

Prep is a browser-based interview practice application built with Python and
Flask. It presents curated questions from five interview areas and evaluates a
candidate's written answer using TF-IDF text features, cosine similarity, and
key-concept coverage. Instead of returning only a score, the application
identifies concepts that appear to be covered or missing and gives concise
feedback.

The project uses SQLite to retain questions, registered users, and practice
results. Registration and login use Werkzeug password hashing, signed Flask
sessions, and CSRF protection. A user's dashboard and practice history are
scoped to that account. The system is designed as an explainable student
project: its scoring method is transparent, but it is a lexical baseline and
does not claim perfect semantic understanding.

## 1. Introduction

Interview preparation often involves reading sample answers without practising
how to formulate a response. Prep provides a simple practice loop: select an
interview category and difficulty, answer a question, review a score breakdown,
and repeat. The application combines an existing curated CSV question bank and
TF-IDF/cosine-similarity evaluation with a responsive web interface, user
accounts, SQLite persistence, and a results dashboard.

## 2. Problem Statement

Students need an accessible way to rehearse interview questions and receive
useful, repeatable feedback. A basic correct/incorrect result does not show
which important ideas were included or what should be added. Prep addresses
this by combining a similarity estimate with explicit concept coverage and
retaining results so users can review their practice.

## 3. Objectives

- Provide practice questions in HR / Behavioral, CS Fundamentals, Python
  Programming, Machine Learning Basics, and System Design.
- Organize questions into Beginner, Intermediate, and Advanced levels.
- Estimate the overlap between a candidate's response and a curated reference
  answer using TF-IDF and cosine similarity.
- Show covered concepts, missing concepts, a final score, and improvement
  feedback.
- Store questions and scored attempts in SQLite and allow question CRUD through
  a Flask JSON API.
- Provide registration, login, logout, and account-specific practice history.
- Keep the design, scoring method, and setup understandable for demonstration
  and viva evaluation.

## 4. Scope

Prep is a local academic prototype. It evaluates typed answers against curated
reference material. It does not conduct speech interviews, use a paid AI API,
or guarantee that a score measures a person's full understanding. Users need
an account to practise and view private results. Question bank reads are
available to the application; create, update, and delete operations require a
logged-in account. This version does not define administrator roles.

## 5. Technology Stack

| Area | Technology |
| --- | --- |
| Application/backend | Python 3, Flask |
| Text processing | scikit-learn TF-IDF vectorization and cosine similarity |
| Database | SQLite and Python's `sqlite3` module |
| Authentication | Werkzeug password hashing, Flask signed session |
| CSRF protection | Flask-WTF |
| User interface | HTML, CSS, Bootstrap 5, JavaScript |
| Charts | Chart.js |
| Tests | Python `unittest`, Flask test client, temporary SQLite databases |

The external Bootstrap and Chart.js browser assets are loaded from public CDNs.

## 6. System Architecture

```text
Browser
  ├── Public home, registration, and login pages
  └── Authenticated practice and dashboard interface
          │ HTML forms and JSON API requests (CSRF token on writes)
          ▼
Flask application (app/app.py)
  ├── Registration, login, logout, and access control
  ├── Question and answer REST routes
  ├── Results/dashboard routes with per-user filters
  └── Answer evaluation ──────────────► model/answer_scorer.py
          │
          ▼
SQLite persistence (app/database.py)
  ├── users
  ├── questions  ◄── initial/repeatable import from CSV
  └── practice_results
```

### Main modules

- **`app/app.py`:** Flask app factory, request validation, authentication
  routes, access control, REST endpoints, and result aggregation.
- **`app/database.py`:** SQLite schema initialization and migration, CSV
  import, and database result formatting.
- **`model/answer_scorer.py`:** TF-IDF/cosine-similarity scoring, concept
  coverage, length adjustment, and feedback generation.
- **`data/question_bank.csv`:** Human-curated source questions, reference
  answers, concepts, and difficulty.
- **`data/build_question_bank.py`:** Rebuilds the CSV from the editable Python
  question list.
- **`app/templates/` and `app/static/`:** Public and authenticated pages,
  responsive styling, password visibility control, practice interactions,
  and dashboard charts.
- **`tests/test_app.py`:** Scorer, API, authentication, CSRF, persistence,
  migration, and privacy tests.

## 7. Database Design

The application creates `data/prep.db` at startup when needed.

### `users`

| Column | Purpose |
| --- | --- |
| `id` | Integer primary key |
| `full_name` | User's display name |
| `email` | Unique email address, compared case-insensitively |
| `password_hash` | Werkzeug-generated password hash; plaintext is not stored |
| `created_at` | Account creation timestamp |

### `questions`

| Column | Purpose |
| --- | --- |
| `id` | Integer primary key |
| `category` | One of the five supported interview categories |
| `difficulty` | Beginner, Intermediate, or Advanced |
| `question` | Prompt shown to the user |
| `model_answer` | Curated answer used by the scorer |
| `key_points` | Comma-separated concepts for coverage feedback |
| `created_at` | Record creation timestamp |

### `practice_results`

| Column | Purpose |
| --- | --- |
| `id` | Integer primary key |
| `user_id` | Owning account; references `users.id` |
| `session_id` | Identifier grouping a practice session |
| `question_id` | Related question |
| `answer` | Submitted response |
| `similarity_score`, `keyword_score`, `final_score` | Evaluation scores |
| `covered_points`, `missing_points`, `feedback` | Saved feedback details |
| `created_at` | Attempt timestamp |

An initialization migration adds the nullable `user_id` column to older
practice-results tables without deleting saved attempts. Historical rows that
were created before accounts existed remain unassigned and are not exposed as
belonging to a user.

## 8. Answer-Scoring Method

For each non-empty candidate response, the scorer computes the following:

1. **TF-IDF similarity.** A `TfidfVectorizer` with English stop-word removal
   and unigram/bigram features is fitted on the candidate answer and the
   question's reference answer. Cosine similarity between the two vectors is
   converted to a percentage from 0 to 100. If the vectorizer has no usable
   vocabulary, similarity is zero.
2. **Key-concept coverage.** Each comma-separated key point and the candidate
   answer are tokenized into lowercase alphanumeric terms. A concept is marked
   covered when at least half of its significant terms occur as whole tokens
   in the candidate answer. Coverage is the proportion of covered concepts,
   converted to a percentage.
3. **Answer-length multiplier.** Fewer than 8 words uses a multiplier of `0.5`;
   8–14 words uses `0.8`; 15 or more words uses `1.0`.
4. **Weighted final score.** The default similarity and coverage weights are
   `0.55` and `0.45`. The formula is:

   ```text
   final_score = round(
       (normalized_similarity_weight × similarity_score
        + normalized_coverage_weight × coverage_score)
       × length_multiplier
   )
   ```

   The result is bounded to 0–100. Weights can be configured with
   `PREP_SIMILARITY_WEIGHT` and `PREP_COVERAGE_WEIGHT`; the pair must be
   non-negative and have a positive total, and is normalized before use.

### Interpretation and limitations

TF-IDF measures lexical feature overlap, not meaning in a human sense. A
correct answer expressed with synonyms or different wording can receive a
lower similarity/coverage score. Conversely, using a concept term without
explaining it can count as coverage. Scores should be treated as practice
signals; human review remains important.

## 9. Authentication and Data Protection

- Registration checks required fields, email format, input lengths, minimum
  password length, and confirmation matching on the server.
- Email uniqueness is enforced by SQLite and checked without regard to case.
- Passwords are stored as Werkzeug password hashes, never as plaintext.
- Successful login clears the prior session, stores the user's database ID,
  and sets a session lifetime.
- Session cookies are HTTP-only and use `SameSite=Lax`. HTTPS deployments
  should set `PREP_COOKIE_SECURE=1`.
- Flask-WTF protects form submissions and state-changing API requests against
  CSRF. The practice JavaScript reads the page token and sends it using the
  `X-CSRFToken` header.
- Protected routes redirect browser users to login and return HTTP `401` for
  unauthenticated API requests.
- Result-list, summary, and individual-result database queries filter by the
  authenticated user's ID. Each user's results are isolated from other
  accounts.
- A stable `PREP_SECRET_KEY` should be configured before deployment; the
  development fallback creates a new key at process start and therefore
  invalidates existing sessions on restart.

This mini project is not a hardened production service. In particular, it has
no email verification, password reset, login rate limiting, role management,
or deployment-grade hosting configuration.

## 10. API Summary

| Method | Path | Function |
| --- | --- | --- |
| `GET` | `/api/categories` | Get supported categories and difficulties |
| `GET` | `/api/questions` | Filter questions by category/difficulty |
| `POST` | `/api/questions` | Create a question (login and CSRF required) |
| `GET` | `/api/questions/<id>` | Read a question including its reference material |
| `PUT` | `/api/questions/<id>` | Update a question (login and CSRF required) |
| `DELETE` | `/api/questions/<id>` | Delete an unused question (login and CSRF required) |
| `POST` | `/api/answers` | Evaluate and save an answer (login and CSRF required) |
| `GET` | `/api/results` | Read the current user's saved results |
| `GET` | `/api/results/summary` | Read the current user's dashboard summary |
| `GET` | `/api/results/<id>` | Read one of the current user's results |

Validation failures return `400`, unauthenticated API writes/reads return
`401`, missing records return `404`, and deleting a question referenced by
saved results returns `409`.

## 11. Setup and Execution

Python 3.10 or later is recommended. From the project root:

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Set a stable session secret for local use (macOS/Linux):

```bash
export PREP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

Start the application and open the local address:

```bash
python -m app.app
# Visit http://127.0.0.1:5050
```

Run the automated test suite from the project root:

```bash
python -m unittest discover -s tests -v
```

The CSV can be regenerated after editing the source question list:

```bash
python data/build_question_bank.py
```

At application startup, questions missing from SQLite are imported from the
CSV; existing records and practice history are retained.

## 12. Testing

The project's `unittest` suite was run during preparation of this report:

```text
Ran 13 tests
OK
```

The tests include:

- Scoring empty and non-empty answers, concept feedback, and configurable
  weights.
- Registration validation, password hashing, and case-insensitive duplicate
  email rejection.
- Invalid login, successful login/session creation, logout, protected pages,
  and private API access.
- CSRF rejection when a token is missing.
- Account-to-account practice-result isolation, including individual result
  lookup.
- Authenticated question CRUD, API validation, and migration of an existing
  results table without losing its rows.

## 13. Future Enhancements

- Add email verification, password recovery, and login rate limiting.
- Add administrator roles for managing the shared question bank.
- Grow and independently review the curated questions and reference answers.
- Explore sentence embeddings as an optional comparison, while retaining
  transparent baselines and honest limitations.
- Add exportable reports, more detailed progress filters, and accessibility
  checks across supported browsers.
- Add deployment configuration and operational security controls before
  exposing the application publicly.

## 14. Conclusion

Prep combines explainable text-based answer evaluation with a complete web
practice flow, account authentication, SQLite persistence, APIs, and
user-specific history. Its compact design keeps the application suitable for
an MCA AI & ML mini-project and makes the scoring formula straightforward to
explain. The project also makes its key limitation explicit: lexical similarity
and concept matching are useful feedback heuristics, not perfect semantic
understanding.

## Viva Quick Notes

- **What does TF-IDF do?** It represents text using term-frequency features
  weighted by how informative terms are across the two texts being compared.
- **Why cosine similarity?** It compares the direction of the TF-IDF vectors,
  giving a normalized measure of feature overlap.
- **Why add key-concept coverage?** Similarity alone does not say which
  expected ideas appear to be missing; coverage provides actionable,
  interpretable feedback.
- **Why is the score not a perfect semantic measure?** Word-based features can
  miss synonyms and context, and concept matching does not verify the quality
  of an explanation.
- **How are passwords protected?** Werkzeug password hashing stores a
  one-way hash, and login verifies the submitted password against that hash.
- **How are results private?** Each result is written with the authenticated
  user's ID, and result queries filter by that ID.
