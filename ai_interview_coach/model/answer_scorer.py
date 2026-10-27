"""
answer_scorer.py
-------------------
Scores a candidate's typed answer against the model answer for a given
interview question using two signals:

1. Text similarity (TF-IDF + cosine similarity) between the candidate's
   answer and the model answer -- estimates lexical overlap.
2. Keyword/key-point coverage -- checks how many of the important concepts
   (key_points) for that question actually appear in the candidate's answer,
   giving concrete, explainable feedback ("you didn't mention X").

Also applies a light length/effort heuristic since a one-word answer
shouldn't score well even if it happens to share a term with the model
answer.
"""

import math
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_SIMILARITY_WEIGHT = 0.55
DEFAULT_COVERAGE_WEIGHT = 0.45


def _tokenize_keypoints(key_points: str):
    """key_points is a comma-separated string like 'bias, variance, underfitting'."""
    return [kp.strip().lower() for kp in (key_points or "").split(",") if kp.strip()]


def score_answer(
    candidate_answer: str,
    model_answer: str,
    key_points: str,
    similarity_weight: float = DEFAULT_SIMILARITY_WEIGHT,
    coverage_weight: float = DEFAULT_COVERAGE_WEIGHT,
):
    if (
        not math.isfinite(similarity_weight)
        or not math.isfinite(coverage_weight)
        or similarity_weight < 0
        or coverage_weight < 0
        or similarity_weight + coverage_weight == 0
    ):
        raise ValueError("Scoring weights must be non-negative and have a positive total.")

    weight_total = similarity_weight + coverage_weight
    similarity_weight /= weight_total
    coverage_weight /= weight_total
    candidate_answer = candidate_answer.strip()

    if not isinstance(candidate_answer, str):
        raise ValueError("candidate_answer must be a string.")
    if not isinstance(model_answer, str):
        raise ValueError("model_answer must be a string.")
    if not candidate_answer.strip():
        return {
            "similarity_score": 0,
            "keyword_score": 0,
            "final_score": 0,
            "covered_points": [],
            "missing_points": _tokenize_keypoints(key_points),
            "feedback": ["No answer provided."],
        }

    # ---------- 1. Semantic similarity via TF-IDF + cosine similarity ----------
    vectorizer = TfidfVectorizer(lowercase=True, stop_words="english", ngram_range=(1, 2))
    try:
        tfidf = vectorizer.fit_transform([candidate_answer, model_answer])
        similarity = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    except ValueError:
        # happens if both texts have no vocabulary in common after stopword removal
        similarity = 0.0

    similarity_score = round(similarity * 100)

    # ---------- 2. Keyword / key-point coverage ----------
    points = _tokenize_keypoints(key_points)
    candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate_answer.lower()))
    covered = []
    missing = []
    for point in points:
        point_tokens = set(re.findall(r"[a-z0-9]+", point))
        significant_tokens = {token for token in point_tokens if len(token) > 2}
        if not significant_tokens:
            significant_tokens = point_tokens
        hits = len(significant_tokens & candidate_tokens)
        if significant_tokens and hits >= (len(significant_tokens) + 1) // 2:
            covered.append(point)
        else:
            missing.append(point)

    keyword_score = round((len(covered) / len(points)) * 100) if points else 0

    # ---------- 3. Length/effort heuristic ----------
    word_count = len(candidate_answer.split())
    if word_count < 8:
        length_penalty = 0.5  # too short, cap effective score
    elif word_count < 15:
        length_penalty = 0.8
    else:
        length_penalty = 1.0

    # ---------- Blend into final score ----------
    final_score = round(
        (similarity_weight * similarity_score + coverage_weight * keyword_score) * length_penalty
    )
    final_score = max(0, min(100, final_score))

    # ---------- Feedback generation ----------
    feedback = []
    if word_count < 8:
        feedback.append("Your answer is quite short — try to explain your reasoning, not just state a term.")
    if missing:
        feedback.append(f"You could strengthen this by mentioning: {', '.join(missing)}.")
    if similarity_score < 30 and word_count >= 8:
        feedback.append("Your answer's overall direction seems different from what's typically expected — double check you're addressing the actual question asked.")
    if not feedback:
        feedback.append("Solid answer — covers the key concepts well and is clearly explained.")

    return {
        "similarity_score": similarity_score,
        "keyword_score": keyword_score,
        "final_score": final_score,
        "length_penalty": length_penalty,
        "word_count": word_count,
        "covered_points": covered,
        "missing_points": missing,
        "feedback": feedback,
    }
