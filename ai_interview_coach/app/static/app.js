const SESSION_LENGTH = 5;
const categorySelect = document.getElementById("categorySelect");
const difficultySelect = document.getElementById("difficultySelect");
const questionPanel = document.getElementById("questionPanel");
const questionText = document.getElementById("questionText");
const answerInput = document.getElementById("answerInput");
const submitBtn = document.getElementById("submitBtn");
const nextBtn = document.getElementById("nextBtn");
const resultPanel = document.getElementById("resultPanel");
const errorMessage = document.getElementById("errorMessage");

let currentQuestion = null;
let sessionId = null;
let sessionAnswers = [];
let seenQuestionIds = new Set();
let trendChart = null;
let categoryChart = null;

function newSessionId() {
  return window.crypto?.randomUUID?.() || `prep-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function api(url, options = {}) {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      ...(options.headers || {}),
    },
  });
  const data = response.status === 204 ? {} : await response.json();
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.textContent = "";
  errorMessage.hidden = true;
}

function updateWordCount() {
  const count = answerInput.value.trim().split(/\s+/).filter(Boolean).length;
  document.getElementById("wordCount").textContent = `${count} ${count === 1 ? "word" : "words"}`;
}

async function getNextQuestion() {
  clearError();
  const params = new URLSearchParams({
    category: categorySelect.value,
    difficulty: difficultySelect.value,
  });
  try {
    const data = await api(`/api/questions?${params}`);
    if (!data.questions.length) {
      categorySelect.disabled = false;
      difficultySelect.disabled = false;
      document.getElementById("startState").hidden = false;
      questionPanel.hidden = true;
      showError("There are no questions for this category and difficulty yet. Try another level.");
      return;
    }
    let available = data.questions.filter((question) => !seenQuestionIds.has(question.id));
    if (!available.length) {
      seenQuestionIds.clear();
      available = data.questions;
    }
    currentQuestion = available[Math.floor(Math.random() * available.length)];
    seenQuestionIds.add(currentQuestion.id);
    questionText.textContent = currentQuestion.question;
    document.getElementById("questionCategory").textContent = currentQuestion.category;
    document.getElementById("questionDifficulty").textContent = currentQuestion.difficulty;
    document.getElementById("questionCount").textContent = `Question ${sessionAnswers.length + 1} of ${SESSION_LENGTH}`;
    answerInput.value = "";
    updateWordCount();
    resultPanel.hidden = true;
    nextBtn.hidden = true;
    submitBtn.hidden = false;
    submitBtn.disabled = false;
    questionPanel.hidden = false;
    document.getElementById("startState").hidden = true;
    answerInput.focus();
  } catch (error) {
    showError(error.message);
  }
}

async function startSession() {
  sessionId = newSessionId();
  sessionAnswers = [];
  seenQuestionIds = new Set();
  document.getElementById("sessionSummary").hidden = true;
  categorySelect.disabled = true;
  difficultySelect.disabled = true;
  await getNextQuestion();
}

function populateList(elementId, values, emptyText) {
  const list = document.getElementById(elementId);
  list.replaceChildren();
  if (!values.length) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    list.appendChild(item);
    return;
  }
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  });
}

function verdict(score) {
  if (score >= 80) return "Excellent foundation";
  if (score >= 60) return "Good progress";
  if (score >= 35) return "Keep building depth";
  return "A chance to strengthen";
}

function renderEvaluation(result) {
  const score = result.final_score;
  const ring = document.getElementById("scoreRing");
  ring.style.borderColor = score >= 65 ? "#98dec3" : score >= 35 ? "#f2d297" : "#efb1b1";
  ring.style.color = score >= 65 ? "#16865f" : score >= 35 ? "#a36b0b" : "#ba4f4f";
  document.getElementById("finalScore").textContent = score;
  document.getElementById("scoreVerdict").textContent = verdict(score);
  document.getElementById("similarityValue").textContent = `${result.similarity_score}%`;
  document.getElementById("coverageValue").textContent = `${result.keyword_score}%`;
  document.getElementById("similarityBar").style.width = `${result.similarity_score}%`;
  document.getElementById("coverageBar").style.width = `${result.keyword_score}%`;
  populateList("coveredList", result.covered_points, "No key concepts detected yet.");
  populateList("missingList", result.missing_points, "You covered all listed concepts.");
  populateList("feedbackList", result.feedback, "Keep practicing.");
  document.getElementById("modelAnswer").textContent = result.model_answer || "Reference answer unavailable.";
  resultPanel.hidden = false;
}

async function evaluateAnswer() {
  clearError();
  if (!currentQuestion) return showError("Start a practice session first.");
  if (!answerInput.value.trim()) return showError("Write an answer before asking for feedback.");
  submitBtn.disabled = true;
  submitBtn.textContent = "Evaluating…";
  try {
    const data = await api("/api/answers", {
      method: "POST",
      body: JSON.stringify({
        question_id: currentQuestion.id,
        answer: answerInput.value,
        session_id: sessionId,
      }),
    });
    const result = data.result;
    sessionAnswers.push(result);
    renderEvaluation(result);
    submitBtn.hidden = true;
    if (sessionAnswers.length < SESSION_LENGTH) {
      nextBtn.hidden = false;
    } else {
      nextBtn.hidden = true;
      await completeSession();
    }
    await loadSnapshot();
  } catch (error) {
    submitBtn.disabled = false;
    showError(error.message);
  } finally {
    submitBtn.textContent = "Evaluate my answer →";
  }
}

async function completeSession() {
  const average = Math.round(sessionAnswers.reduce((total, item) => total + item.final_score, 0) / sessionAnswers.length);
  document.getElementById("sessionAverage").textContent = `${average}/100`;
  const list = document.getElementById("sessionResults");
  list.replaceChildren();
  sessionAnswers.forEach((result, index) => {
    const row = document.createElement("div");
    row.className = "session-result-row";
    const details = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${result.question}`;
    const category = document.createElement("small");
    category.textContent = `${result.category} · ${result.difficulty}`;
    details.append(title, category);
    const score = document.createElement("span");
    score.className = "result-score-badge";
    score.textContent = `${result.final_score}`;
    row.append(details, score);
    list.appendChild(row);
  });
  document.getElementById("sessionSummary").hidden = false;
  categorySelect.disabled = false;
  difficultySelect.disabled = false;
  document.getElementById("sessionSummary").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadSnapshot() {
  try {
    const summary = await api("/api/results/summary");
    document.getElementById("attemptCount").textContent = summary.attempts;
    document.getElementById("averageScore").textContent = summary.attempts ? `${summary.average_score}/100` : "—";
    document.getElementById("bestScore").textContent = summary.attempts ? `${summary.best_score}/100` : "—";
    document.getElementById("dashboardAttempts").textContent = summary.attempts;
    document.getElementById("dashboardAverage").textContent = summary.attempts ? `${summary.average_score}/100` : "—";
    document.getElementById("dashboardBest").textContent = summary.attempts ? `${summary.best_score}/100` : "—";
    return summary;
  } catch (error) {
    showError(`Could not load your practice dashboard: ${error.message}`);
    return null;
  }
}

function renderHistory(results) {
  const container = document.getElementById("historyList");
  container.replaceChildren();
  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "empty-history";
    empty.textContent = "No answers yet. Complete a practice question and your history will appear here.";
    container.appendChild(empty);
    return;
  }
  results.forEach((result) => {
    const row = document.createElement("div");
    row.className = "history-row";
    const question = document.createElement("div");
    question.className = "history-question";
    question.textContent = result.question;
    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = `${result.category} · ${result.difficulty} · ${result.created_at}`;
    const score = document.createElement("div");
    score.className = "history-score";
    score.textContent = `${result.final_score}/100`;
    row.append(question, meta, score);
    container.appendChild(row);
  });
}

function drawCharts(summary) {
  if (!window.Chart) return;
  if (trendChart) trendChart.destroy();
  if (categoryChart) categoryChart.destroy();
  trendChart = new Chart(document.getElementById("trendChart"), {
    type: "line",
    data: {
      labels: summary.score_trend.map((item) => item.date.slice(5, 16)),
      datasets: [{ label: "Score", data: summary.score_trend.map((item) => item.score), borderColor: "#4569e8", backgroundColor: "#4569e81c", fill: true, tension: 0.35, pointRadius: 3 }],
    },
    options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 100, ticks: { stepSize: 20 } } }, plugins: { legend: { display: false } } },
  });
  categoryChart = new Chart(document.getElementById("categoryChart"), {
    type: "bar",
    data: {
      labels: summary.category_stats.map((item) => item.category),
      datasets: [{ label: "Average score", data: summary.category_stats.map((item) => item.average_score), backgroundColor: "#7e95ee", borderRadius: 5 }],
    },
    options: { indexAxis: "y", maintainAspectRatio: false, scales: { x: { min: 0, max: 100, ticks: { stepSize: 20 } } }, plugins: { legend: { display: false } } },
  });
}

async function openDashboard() {
  document.getElementById("practicePage").hidden = true;
  document.getElementById("dashboardPage").hidden = false;
  document.getElementById("practiceNav").classList.remove("active");
  document.getElementById("dashboardNav").classList.add("active");
  try {
    const [summary, data] = await Promise.all([loadSnapshot(), api("/api/results?limit=20")]);
    if (summary) drawCharts(summary);
    renderHistory(data.results);
  } catch (error) {
    const history = document.getElementById("historyList");
    history.textContent = `Could not load your practice history: ${error.message}`;
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openPractice() {
  document.getElementById("practicePage").hidden = false;
  document.getElementById("dashboardPage").hidden = true;
  document.getElementById("practiceNav").classList.add("active");
  document.getElementById("dashboardNav").classList.remove("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.getElementById("startBtn").addEventListener("click", startSession);
document.getElementById("retryBtn").addEventListener("click", startSession);
document.getElementById("submitBtn").addEventListener("click", evaluateAnswer);
document.getElementById("nextBtn").addEventListener("click", getNextQuestion);
document.getElementById("practiceNav").addEventListener("click", openPractice);
document.getElementById("dashboardNav").addEventListener("click", openDashboard);
document.getElementById("viewDashboardBtn").addEventListener("click", openDashboard);
document.getElementById("backToPracticeBtn").addEventListener("click", openPractice);
answerInput.addEventListener("input", updateWordCount);

loadSnapshot();
