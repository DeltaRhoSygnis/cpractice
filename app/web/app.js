"use strict";

/**
 * CPractice frontend.
 *
 * No framework, no CDN, no build step. Hash routing keeps it to one page and
 * works when served from FastAPI's StaticFiles mount.
 *
 * Two rules the UI must respect:
 *  - hidden test content is never requested or rendered; the API does not send
 *    it, and the UI never implies it exists beyond a count;
 *  - facts (test results) and guidance (hints) are visually separate.
 */

/* ------------------------------------------------------------------ utils */

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
}

const TOAST_ICON = { ok: "✔", fail: "✘", warn: "!" };
const TOAST_WORD = { ok: "Success", fail: "Error", warn: "Warning" };

function toast(message, kind = "ok") {
  const region = $("#toast-region");
  if (!region) return;
  // Pass/fail must never be carried by colour alone: pair the tint with an
  // icon, exactly as the status lines do. The whole toast exposes one clean
  // label, and failures are announced assertively (role="alert") rather than
  // politely, because a failed submit needs to be heard now.
  const node = el("div", {
    class: `toast toast--${kind}`,
    role: kind === "fail" ? "alert" : "status",
    "aria-live": kind === "fail" ? "assertive" : "polite",
    "aria-label": `${TOAST_WORD[kind] || "Notice"}: ${message}`,
  }, [
    el("span", { class: "toast__icon", "aria-hidden": "true", text: TOAST_ICON[kind] || "✔" }),
    el("span", { "aria-hidden": "true", text: message }),
  ]);
  region.append(node);
  const remove = () => node.remove();
  setTimeout(() => {
    node.classList.add("toast--leaving");
    node.addEventListener("animationend", remove, { once: true });
    // Fallback for reduced-motion / no-animation environments.
    setTimeout(remove, 200);
  }, 5000);
}

/* ------------------------------------------------------------------- api */

const api = {
  async request(method, path, body, signal) {
    const options = { method, headers: { Accept: "application/json" } };
    if (signal) options.signal = signal;
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(`/api${path}`, options);

    let payload = null;
    const text = await response.text();
    if (text) {
      try { payload = JSON.parse(text); } catch { payload = { detail: text }; }
    }

    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = response.status;
      throw error;
    }
    return payload;
  },
  health: () => api.request("GET", "/health"),
  listProblems: () => api.request("GET", "/problems"),
  getProblem: (id) => api.request("GET", `/problems/${encodeURIComponent(id)}`),
  submit: (id, source, hintsUsed) =>
    api.request("POST", `/problems/${encodeURIComponent(id)}/submit`, {
      source, hints_used: hintsUsed,
    }),
  hint: (id, hintsUsed, source, failure) =>
    api.request("POST", `/problems/${encodeURIComponent(id)}/hint`, {
      hints_used: hintsUsed, source: source || "", failure_summary: failure || "",
    }),
  solution: (id) =>
    api.request("POST", `/problems/${encodeURIComponent(id)}/solution`, { confirm: true }),
  attempts: (limit = 20) => api.request("GET", `/attempts?limit=${limit}`),
  progress: () => api.request("GET", "/progress"),
  recommendations: () => api.request("GET", "/recommendations"),
  usage: () => api.request("GET", "/usage"),
  generate: (params, signal) => api.request("POST", "/problems/generate", params, signal),
};

/* --------------------------------------------------------------- helpers */

const STATUS_ICON = { ok: "✔", warn: "!", fail: "✘", pending: "…" };

/* Learner-facing labels for engine vocabulary. Showing a raw enum is how a
   personal tool starts to feel like a CI dashboard. */
const STATUS_LABEL = {
  validated: "ready to use",
  needs_review: "not verified yet",
  rejected: "was discarded",
};
const VERDICT_LABEL = {
  passed: "all passed",
  partial: "partly passing",
  all_failed: "none passed",
  compilation_failed: "didn't compile",
};
const FAILURE_LABEL = {
  wrong_answer: "wrong output",
  runtime_error: "crashed while running",
  timeout: "took too long",
  output_limit_exceeded: "printed too much output",
  compilation_error: "didn't compile",
  internal_error: "grader error",
};

/* Learner-facing labels for the pedagogy `exercise_role` enum
   (app/schemas/pedagogy.py::ExerciseRole). "core_reasoning" is the vocabulary a
   reviewer uses, not a learner. */
const ROLE_LABEL = {
  core_reasoning: "core reasoning",
  diagnostic_warmup: "warm-up",
  transfer: "transfer problem",
  challenge: "challenge",
  debugging: "debugging",
  reflection: "reflection",
};

/** "3 attempts" / "1 attempt" — never the machine-flavoured "(s)". */
const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;


/* Checker states. Like every other status in this UI, pass/fail/blocked is
   carried by icon + text + colour, never by colour alone: each row pairs a
   glyph with a visually-hidden status word so a screen reader hears the
   outcome rather than relying on the tint. */
const CHECK_ICON = { pass: "✔", fail: "✘", blocked: "⋯" };
const CHECK_WORD = { pass: "Passed", fail: "Failed", blocked: "Blocked" };
const CHECK_CAUSE = {
  "compilation failed": "can't check until the program compiles",
  "submission not found": "nothing was submitted",
  "did not pass": "the program produced the wrong output",
};

function loading(label = "Loading…") {
  return el("div", { class: "card" }, [
    el("span", { class: "spinner", "aria-hidden": "true" }),
    el("span", { class: "muted", text: ` ${label}` }),
  ]);
}

function errorCard(message, retry, status) {
  // Name the class of failure so the learner knows whether it was them or the
  // server, and always give a next step. Prefer the HTTP status when present;
  // fall back to a message heuristic only when we have nothing better.
  const serverSide =
    (typeof status === "number" && status >= 500) ||
    (typeof status !== "number" && /fetch|network|reach/i.test(message));
  const heading = serverSide ? "Couldn't reach the grader" : "That request wasn't accepted";
  const children = [
    el("h2", { text: heading }),
    el("p", { class: "muted", text: message }),
    el("p", { class: "small muted", text: serverSide
      ? "The server had a problem, not your code. Try again in a moment."
      : "Check the status line on the Dashboard if this keeps happening." }),
  ];
  if (retry) {
    children.push(el("button", { class: "secondary", text: "Retry", onclick: retry }));
  }
  return el("div", { class: "card state--error" }, children);
}

function emptyState(message) {
  return el("p", { class: "empty", text: message });
}

/** Escape-free code block: always assign via textContent. */
function codeBlock(text, className = "diagnostics") {
  return el("pre", { class: className, text });
}

/** Persisted draft per problem, so a mistake is never lost on reload. */
const draftKey = (id) => `cpractice:draft:${id}`;
const saveDraft = (id, source) => {
  try { localStorage.setItem(draftKey(id), source); } catch { /* quota */ }
};
const loadDraft = (id) => {
  try { return localStorage.getItem(draftKey(id)) || ""; } catch { return ""; }
};

/* ---------------------------------------------------------------- views */

const views = {};

/* --- dashboard --- */
views.dashboard = async () => {
  const container = el("div");
  container.append(
    el("h1", { text: "Dashboard" }),
    el("p", { class: "subtitle", text: "AI generates and explains. Deterministic software grades." }),
  );

  // A learner needs three facts at a glance, not an infrastructure panel:
  // can I be graded, is the AI on, and where does my work live.
  const statusStrip = el("p", { class: "status-strip", role: "status" }, [
    el("span", { class: "status-strip__item", text: "Checking backend…" }),
  ]);
  container.append(statusStrip);

  const actionCard = el("div", { class: "card" }, [el("h2", { text: "Get a problem" })]);
  const topic = el("input", { type: "text", value: "loops", id: "gen-topic" });
  const difficulty = el("select", { id: "gen-difficulty" }, [
    el("option", { value: "beginner", text: "Beginner" }),
    el("option", { value: "intermediate", text: "Intermediate" }),
    el("option", { value: "advanced", text: "Advanced" }),
  ]);
  const generateBtn = el("button", { text: "Generate problem" });
  const generateOut = el("div");
  let activeController = null;

  generateBtn.addEventListener("click", async () => {
    // Guard re-entry on the in-flight controller, not just the disabled button.
    if (activeController) return;
    generateBtn.disabled = true;
    generateBtn.textContent = "Generating…";

    // Staged copy keyed on elapsed time. A rising counter is the cheapest proof
    // the work is still alive, and honest stage text beats a single "~30s".
    const started = Date.now();
    const progress = el("p", { class: "small muted" }, [
      el("span", { class: "spinner", "aria-hidden": "true" }),
      el("span", { text: " Writing your problem…" }),
      el("span", { class: "tabular", text: " 0s" }),
    ]);
    const cancelBtn = el("button", { class: "secondary", text: "Cancel" });
    generateOut.replaceChildren(progress, el("div", { class: "button-row" }, [cancelBtn]));

    const timer = setInterval(() => {
      const secs = Math.floor((Date.now() - started) / 1000);
      progress.lastChild.textContent = ` ${secs}s`;
      const stage = progress.children[1];
      if (secs >= 45) stage.textContent = " Taking longer than usual — you can keep waiting or cancel.";
      else if (secs >= 20) stage.textContent = " Still working. Some problems take a minute.";
      else if (secs >= 8) stage.textContent = " Checking it compiles and passes its own tests…";
    }, 1000);

    const controller = new AbortController();
    activeController = controller;
    cancelBtn.addEventListener("click", () => controller.abort());

    const cleanup = () => {
      clearInterval(timer);
      activeController = null;
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate problem";
    };

    try {
      const result = await api.generate({
        topic: topic.value.trim() || "loops",
        difficulty: difficulty.value,
      }, controller.signal);
      if (result.accepted) {
        toast("New problem ready", "ok");
        const ref = result.reference;
        generateOut.replaceChildren(
          el("div", { class: "verdict verdict--pass" }, [
            el("span", { class: "verdict__icon", "aria-hidden": "true", text: "✔" }),
            el("span", {
              text: `Ready. Its own reference solution passes all ${ref.total} tests.`,
            }),
          ]),
          el("div", { class: "button-row" }, [
            el("button", {
              text: "Open the problem →",
              onclick: () => { location.hash = `#/problem/${encodeURIComponent(result.problem_id)}`; },
            }),
          ]),
        );
        // The new problem changes recommendations and the problem list, so
        // refresh both rather than leaving stale content on screen.
        await Promise.all([refreshProblems(), refreshRecommendations()]);
      } else {
        // A quality-gate rejection is a tool-side event, not the learner's
        // mistake. Say so plainly, then tuck the engine codes away.
        generateOut.replaceChildren(
          el("div", { class: "verdict verdict--fail" }, [
            el("span", { class: "verdict__icon", "aria-hidden": "true", text: "✘" }),
            el("span", {
              text: "The AI wrote a problem that didn't pass its own tests, so it wasn't kept.",
            }),
          ]),
          el("p", { class: "small muted", text:
            "This isn't your fault. Try again, or pick a different topic or difficulty." }),
          el("details", { class: "disclosure" }, [
            el("summary", { text: "Why it was discarded" }),
            el("ul", { class: "test-list" },
              (result.errors || []).map((e) =>
                el("li", { class: "test-row" }, [
                  el("span", { class: "test-row__icon", "aria-hidden": "true", text: "!" }),
                  el("span", { class: "test-row__body" }, [
                    el("div", { class: "test-row__name", text: e.code }),
                    el("div", { class: "test-row__detail", text: e.message }),
                  ]),
                ]))),
          ]),
        );
      }
    } catch (error) {
      if (error.name === "AbortError") {
        generateOut.replaceChildren(
          el("p", { class: "small muted", text: "Generation cancelled. Nothing was saved." }),
        );
      } else {
        generateOut.replaceChildren(errorCard(error.message, null, error.status));
        toast(error.message, "fail");
      }
    } finally {
      cleanup();
    }
  });

  actionCard.append(
    el("div", { class: "field-row" }, [
      el("div", { class: "field" }, [el("label", { for: "gen-topic", text: "Topic" }), topic]),
      el("div", { class: "field" }, [
        el("label", { for: "gen-difficulty", text: "Difficulty" }), difficulty,
      ]),
    ]),
    el("div", { class: "button-row" }, [generateBtn]),
    generateOut,
  );
  // Generation is powerful and rarely the first step; keep it behind an
  // explicit door instead of opening the product with a form.
  container.append(
    el("details", { class: "advanced" }, [
      el("summary", { text: "Advanced: generate or import a problem" }),
      actionCard,
    ]),
  );

  const recCard = el("div", { class: "card" }, [el("h2", { text: "Recommended next" })]);
  container.append(recCard);

  const problemsCard = el("div", { class: "card" }, [el("h2", { text: "Your problems" })]);
  container.append(problemsCard);

  const recentCard = el("div", { class: "card" }, [el("h2", { text: "Recent attempts" })]);
  container.append(recentCard);

  // --- refreshable loaders -------------------------------------------------
  // Kept as named functions so generating a problem can refresh the affected
  // lists instead of leaving stale content on screen.

  async function refreshRecommendations() {
    recCard.replaceChildren(el("h2", { text: "Recommended next" }));
    try {
      const data = await api.recommendations();
      if (!data.count) {
        recCard.append(emptyState(
          data.evidence_based === false
            ? "No suggestions yet. Generate or pick a problem to begin."
            : "Nothing new to recommend right now.",
        ));
        return;
      }
      const list = el("ul", { class: "problem-list" });
      for (const rec of data.recommendations) {
        list.append(
          el("li", { class: "problem-item" }, [
            el("a", { href: `#/problem/${encodeURIComponent(rec.problem_id)}` }, [
              el("div", { class: "problem-item__title", text: rec.title }),
              el("div", { class: "problem-item__meta", text: rec.reason }),
              el("div", { class: "problem-item__meta" }, [
                el("span", {
                  class: `badge ${rec.exploratory ? "" : "badge--info"}`,
                  text: rec.exploratory ? "breadth suggestion" : "targets a weakness",
                }),
              ]),
            ]),
          ]),
        );
      }
      recCard.append(list);
    } catch (error) {
      recCard.append(emptyState(`Could not load recommendations: ${error.message}`));
    }
  }

  async function refreshProblems() {
    problemsCard.replaceChildren(el("h2", { text: "Your problems" }));
    try {
      const data = await api.listProblems();
      if (!data.count) {
        problemsCard.append(emptyState("No problems yet. The generator on the Dashboard creates one."));
        return;
      }
      const list = el("ul", { class: "problem-list" });
      for (const problem of data.problems) {
        list.append(
          el("li", { class: "problem-item" }, [
            el("a", { href: `#/problem/${encodeURIComponent(problem.id)}` }, [
              el("div", { class: "problem-item__title", text: problem.title }),
              el("div", { class: "problem-item__meta", text:
                `${problem.difficulty} · ${problem.test_count} tests · ` +
                `${(problem.topics || []).join(", ")}` }),
              el("div", { class: "problem-item__meta" }, [
                el("span", {
                  class: `badge ${problem.status === "validated" ? "badge--ok" : "badge--warn"}`,
                  text: STATUS_LABEL[problem.status] || problem.status,
                }),
              ]),
            ]),
          ]),
        );
      }
      problemsCard.append(list);
    } catch (error) {
      problemsCard.append(emptyState(`Could not load problems: ${error.message}`));
    }
  }

  // Data loading, independent so one failure does not blank the page.
  // Every field is optional here on purpose: an older backend must degrade to
  // "unknown", never throw while rendering the page.
  const stripItem = (text, tone) =>
    el("span", {
      class: `status-strip__item${tone ? ` status-strip__item--${tone}` : ""}`,
      text,
    });

  api.health().then((health) => {
    const grading = health?.capabilities?.grading;
    const ai = health?.capabilities?.ai;
    const home = health?.home;

    const gradingText = grading?.ready === true
      ? "Grading ready"
      : grading?.ready === false
        ? "Compiler missing — run cpractice doctor"
        : "Grading status unknown";
    const aiText = ai?.any_key_configured ? "AI on" : "AI offline";
    const homeText = home ? `Data folder: ${home}` : "Data folder: unknown";

    statusStrip.replaceChildren(
      stripItem(gradingText, grading?.ready === false ? "warn" : "ok"),
      stripItem(aiText, ai?.any_key_configured ? "ok" : ""),
      stripItem(homeText, ""),
    );
  }).catch((error) => {
    statusStrip.replaceChildren(stripItem(`Backend unreachable — ${error.message}`, "fail"));
  });

  refreshRecommendations();
  refreshProblems();

  api.attempts(5).then((data) => {
    if (!data.count) {
      recentCard.append(emptyState("No attempts yet — run tests on a problem to see it here."));
      return;
    }
    recentCard.append(attemptTable(data.attempts));
  }).catch((error) => recentCard.append(emptyState(`Could not load attempts: ${error.message}`)));

  return container;
};

/* --- problem list --- */
views.problems = async () => {
  const container = el("div");
  container.append(el("h1", { text: "Problems" }));
  const card = el("div", { class: "card" });
  container.append(card);

  try {
    const data = await api.listProblems();
    if (!data.count) {
      card.append(emptyState("No problems yet. The generator on the Dashboard creates one."));
      return container;
    }
    const list = el("ul", { class: "problem-list" });
    for (const problem of data.problems) {
      list.append(
        el("li", { class: "problem-item" }, [
          el("a", { href: `#/problem/${encodeURIComponent(problem.id)}` }, [
            el("div", { class: "problem-item__title", text: problem.title }),
            el("div", { class: "problem-item__meta", text:
              `${problem.difficulty} · ${problem.test_count} tests · ${(problem.topics || []).join(", ")}` }),
            el("div", { class: "problem-item__meta" }, [
              el("span", {
                class: `badge ${problem.status === "validated" ? "badge--ok" : "badge--warn"}`,
                text: problem.status,
              }),
            ]),
          ]),
        ]),
      );
    }
    card.append(list);
  } catch (error) {
    card.append(errorCard(error.message, null, error.status));
  }
  return container;
};

/* --- problem workspace --- */
views.problem = async (problemId) => {
  const container = el("div");

  let problem;
  try {
    problem = await api.getProblem(problemId);
  } catch (error) {
    container.append(
      el("h1", { text: "Problem" }),
      errorCard(error.message, () => render(), error.status),
    );
    return container;
  }

  container.append(
    el("h1", { text: problem.title }),
    el("p", { class: "subtitle" }, [
      el("span", { class: "badge", text: problem.difficulty }),
      " ",
      el("span", { class: "badge", text: `${problem.public_tests.length} public tests` }),
      " ",
      el("span", {
        class: "badge",
        text: `${problem.hidden_test_count} hidden tests`,
      }),
      problem.topics && problem.topics.length
        ? el("span", { text: ` · ${problem.topics.join(", ")}` })
        : null,
    ]),
  );

  // --- learning objective (only when the problem declares pedagogy) ---
  const objectiveCard = renderObjectiveCard(problem.pedagogy);
  if (objectiveCard) container.append(objectiveCard);

  // --- statement ---
  const statementCard = el("div", { class: "card" }, [el("h2", { text: "Problem statement" })]);
  statementCard.append(el("div", { class: "small", html: renderMarkdown(problem.statement_md) }));
  container.append(statementCard);

  // --- public examples ---
  if (problem.public_tests.length) {
    const examples = el("div", { class: "card" }, [el("h2", { text: "Examples" })]);
    for (const test of problem.public_tests) {
      examples.append(
        el("div", { class: "field-row" }, [
          el("figure", { class: "code-figure" }, [
            el("figcaption", { class: "caption", text: `Input — ${test.name}` }),
            codeBlock(test.stdin || "(none)"),
          ]),
          el("figure", { class: "code-figure" }, [
            el("figcaption", { class: "caption", text: "Expected output" }),
            codeBlock(test.expected_stdout || "(none)"),
          ]),
        ]),
      );
    }
    container.append(examples);
  }

  // --- editor ---
  const editorCard = el("div", { class: "card" }, [el("h2", { text: "Your solution" })]);
  const editor = el("textarea", {
    rows: 16, spellcheck: "false", "aria-label": "C source code",
  });
  editor.value = loadDraft(problem.id) || problem.starter_code || "";
  editor.addEventListener("input", () => saveDraft(problem.id, editor.value));

  const submitBtn = el("button", { text: "Run tests" });
  const clearBtn = el("button", { class: "secondary", text: "Reset to starter" });
  clearBtn.addEventListener("click", () => {
    if (!confirm("Discard your current code and restore the starter?")) return;
    editor.value = problem.starter_code || "";
    saveDraft(problem.id, editor.value);
  });

  const resultRegion = el("div", { "aria-live": "polite", "aria-atomic": "false" });
  let hintsUsed = 0;
  let lastFailure = "";

  editorCard.append(
    el("div", { class: "field" }, [editor]),
    el("div", { class: "button-row" }, [submitBtn, clearBtn]),
    el("p", { class: "small muted", text:
      "Draft saved here on this device — not synced." }),
    resultRegion,
  );
  container.append(editorCard);

  // --- hints ---
  const hintCard = el("div", { class: "card" }, [el("h2", { text: "Hints" })]);
  const ladder = el("ol", { class: "hint-ladder", "aria-label": "Hint progress" });
  const ladderStatus = el("p", { class: "small muted ladder-status" });
  const hintOut = el("div");

  function renderLadder() {
    ladder.replaceChildren();
    const max = problem.max_hint_level || 5;
    for (let level = 1; level <= max; level++) {
      const used = level <= hintsUsed;
      const next = level === hintsUsed + 1;
      const state = used ? "hint-step--used" : next ? "hint-step--next" : "";
      const meaning = used ? "used" : next ? "next available" : "not yet used";
      ladder.append(
        el("li", { class: `hint-step ${state}` }, [
          el("span", { "aria-hidden": "true", text: String(level) }),
          el("span", { class: "visually-hidden", text: `Hint ${level}: ${meaning}` }),
        ]),
      );
    }
    ladderStatus.textContent =
      hintsUsed === 0 ? `Hints: none used yet (${max} available)`
        : `Hints: ${hintsUsed} of ${max} used`;
  }

  function updateHintButton() {
    const max = problem.max_hint_level || 5;
    if (hintsUsed >= max) {
      hintBtn.disabled = true;
      hintBtn.textContent = "No more hints";
    } else {
      hintBtn.disabled = false;
      hintBtn.textContent = hintsUsed + 1 === max
        ? `Get the final hint (${max} of ${max}) →`
        : `Get hint ${hintsUsed + 1} of ${max} →`;
    }
  }

  const hintBtn = el("button", { class: "secondary", text: "Get next hint" });
  hintBtn.addEventListener("click", async () => {
    hintBtn.disabled = true;
    try {
      const result = await api.hint(problem.id, hintsUsed, editor.value, lastFailure);
      hintsUsed = result.hints_used;
      renderLadder();
      const box = el("div", { class: "hint-box" }, [
        el("div", { class: "hint-box__label", text:
          result.is_solution_reveal
            ? `Hint ${result.level} of ${problem.max_hint_level || 5} — the approach`
            : `Hint ${result.level}` }),
        el("div", { text: result.text }),
      ]);
      hintOut.append(box);
      if (!result.next_level) {
        // Exhausting the ladder is the moment to route the learner forward, not
        // dead-end them: say plainly that the solution is now reasonable.
        hintOut.append(el("p", { class: "small muted", text:
          "That was the last hint. If you're still stuck, revealing the solution is a "
          + "reasonable next step — many learners read it, then retype it from memory." }));
      }
    } catch (error) {
      toast(error.message, "warn");
      hintOut.append(el("p", { class: "muted small", text: error.message }));
    } finally {
      updateHintButton();
    }
  });

  const solutionBtn = el("button", { class: "danger", text: "Reveal solution" });
  solutionBtn.addEventListener("click", async () => {
    if (!confirm("Reveal the reference solution? Try to solve it yourself first.")) return;
    try {
      const data = await api.solution(problem.id);
      hintOut.append(
        el("div", { class: "hint-box" }, [
          el("div", { class: "hint-box__label", text: "Reference solution" }),
          codeBlock(data.reference_solution),
          data.solution_explanation
            ? el("p", { class: "small muted", text: data.solution_explanation })
            : null,
        ]),
      );
    } catch (error) {
      toast(error.message, "fail");
    }
  });

  renderLadder();
  updateHintButton();
  hintCard.append(
    ladder,
    ladderStatus,
    el("div", { class: "button-row" }, [hintBtn, solutionBtn]),
    hintOut,
  );
  container.append(hintCard);

  // --- submit handler ---
  submitBtn.addEventListener("click", async () => {
    submitBtn.disabled = true;
    submitBtn.textContent = "Running tests…";
    resultRegion.replaceChildren(loading("Compiling and running tests…"));
    try {
      const result = await api.submit(problem.id, editor.value, hintsUsed);
      lastFailure = (result.failures || [])
        .map((f) => f.test_name).join(", ");
      resultRegion.replaceChildren(renderResult(result));
      toast(
        result.summary.all_passed
          ? `All ${result.summary.total} tests passed`
          : `${result.summary.passed}/${result.summary.total} tests passed`,
        result.summary.all_passed ? "ok" : "warn",
      );
    } catch (error) {
      resultRegion.replaceChildren(errorCard(error.message, null, error.status));
      toast(error.message, "fail");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Run tests";
    }
  });

  return container;
};

/* --- progress --- */
views.progress = async () => {
  const container = el("div");
  container.append(
    el("h1", { text: "Progress" }),
    el("p", { class: "subtitle", text: "How you're doing, based on everything you've submitted." }),
  );

  const summaryCard = el("div", { class: "card" }, [el("h2", { text: "Summary" })]);
  const attemptsCard = el("div", { class: "card" }, [el("h2", { text: "Recent attempts" })]);
  const usageCard = el("div", { class: "card" }, [el("h2", { text: "AI provider usage" })]);
  container.append(summaryCard, attemptsCard, usageCard);

  api.progress().then((data) => {
    const grid = el("div", { class: "stat-grid" });
    const rate = data.test_pass_rate === null ? "—" : `${Math.round(data.test_pass_rate * 100)}%`;
    for (const [value, label] of [
      [String(data.attempts), "Attempts"],
      [String(data.problems_solved), "Problems solved"],
      [String(data.distinct_problems), "Problems tried"],
      [rate, "Tests passed"],
    ]) {
      grid.append(
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: value }),
          el("div", { class: "stat__label", text: label }),
        ]),
      );
    }
    summaryCard.append(grid);

    if (data.weak_topics && data.weak_topics.length) {
      summaryCard.append(el("h3", { text: "Topics to revisit" }));
      const list = el("ul", { class: "test-list" });
      for (const item of data.weak_topics) {
        list.append(
          el("li", { class: "test-row" }, [
            el("span", { class: "test-row__icon", "aria-hidden": "true", text: "!" }),
            el("span", { class: "test-row__body" }, [
              el("div", { class: "test-row__name", text: (item.topics || []).join(", ") }),
              el("div", { class: "test-row__detail",
                text: `failing in ${plural(item.failures, "attempt", "attempts")}` }),
            ]),
          ]),
        );
      }
      summaryCard.append(list);
    }

    const categories = data.failure_categories || {};
    const entries = Object.entries(categories);
    if (entries.length) {
      summaryCard.append(el("h3", { text: "What's going wrong" }));
      const list = el("ul", { class: "test-list" });
      for (const [category, count] of entries) {
        list.append(
          el("li", { class: "test-row" }, [
            el("span", { class: "test-row__icon", "aria-hidden": "true", text: "•" }),
            el("span", { class: "test-row__body" }, [
              el("div", { class: "test-row__name",
                text: FAILURE_LABEL[category] || category.replace(/_/g, " ") }),
              el("div", { class: "test-row__detail",
                text: plural(count, "time", "times") }),
            ]),
          ]),
        );
      }
      summaryCard.append(list);
    }
  }).catch((error) => summaryCard.append(el("p", { class: "muted", text: error.message })));

  api.attempts(25).then((data) => {
    if (!data.count) {
      attemptsCard.append(emptyState("No attempts yet — run tests on a problem to see it here."));
      return;
    }
    attemptsCard.append(attemptTable(data.attempts));
  }).catch((error) => attemptsCard.append(el("p", { class: "muted", text: error.message })));

  api.usage().then((data) => {
    const today = data.today || {};
    const budget = data.budget || {};
    usageCard.append(
      el("div", { class: "stat-grid" }, [
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: String(today.requests || 0) }),
          el("div", { class: "stat__label", text: "Requests today" }),
        ]),
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: String(today.failures || 0) }),
          el("div", { class: "stat__label", text: "Failed requests" }),
        ]),
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: String(today.total_tokens || 0) }),
          el("div", { class: "stat__label", text: "Tokens used" }),
        ]),
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value",
            text: budget.unlimited ? "Unlimited" : String(budget.remaining) }),
          el("div", { class: "stat__label", text: "Requests left" }),
        ]),
      ]),
      el("p", { class: "small muted", text: `Using ${data.model}` }),
    );
  }).catch((error) => usageCard.append(el("p", { class: "muted", text: error.message })));

  return container;
};

/* --------------------------------------------------------- render pieces */

function attemptTable(attempts) {
  const list = el("ul", { class: "test-list" });
  for (const attempt of attempts) {
    const passed = attempt.succeeded;
    list.append(
      el("li", { class: "test-row" }, [
        el("span", {
          class: "test-row__icon",
          "aria-hidden": "true",
          text: passed ? "✔" : "✘",
        }),
        el("span", { class: "test-row__body" }, [
          el("div", { class: "test-row__name" }, [
            el("a", { href: `#/problem/${encodeURIComponent(attempt.problem_id)}`,
                      text: attempt.problem_id }),
            el("span", { class: "muted", text: ` — ${attempt.passed}/${attempt.total} tests` }),
          ]),
          el("div", { class: "test-row__detail", text:
            `${VERDICT_LABEL[attempt.verdict] || attempt.verdict.replace(/_/g, " ")}`
            + ` · ${plural(attempt.hints_used, "hint", "hints")}`
            + ` · ${attempt.created_at}` }),
        ]),
      ]),
    );
  }
  return list;
}

/**
 * "Learning objective" card, built from a problem's optional pedagogy block.
 *
 * The backend only sends `pedagogy` when the problem declares one (older and
 * hand-authored problems omit it), so an absent or empty block must yield no
 * card at all rather than an empty heading. `solution_outline` is deliberately
 * never read here: the API withholds it so the intended approach stays hidden.
 */
function renderObjectiveCard(pedagogy) {
  if (!pedagogy) return null;

  const hasContent =
    (pedagogy.primary_objective || "").trim() ||
    (pedagogy.exercise_role || "").trim() ||
    (pedagogy.prerequisites || []).length ||
    (pedagogy.target_reasoning_moves || []).length ||
    (pedagogy.transfer_goal || "").trim();
  if (!hasContent) return null;

  const card = el("div", { class: "card" }, [el("h2", { text: "Learning objective" })]);

  if ((pedagogy.primary_objective || "").trim()) {
    card.append(el("p", { text: pedagogy.primary_objective }));
  }

  // Role and prerequisites are machine vocabulary; show legible labels/badges.
  const meta = [];
  const role = (pedagogy.exercise_role || "").trim();
  if (role) {
    meta.push(
      el("div", { class: "meta-line" }, [
        el("span", { class: "caption", text: "Role" }),
        el("span", {
          class: "badge badge--info",
          text: ROLE_LABEL[role] || role.replace(/_/g, " "),
        }),
      ]),
    );
  }
  const prerequisites = pedagogy.prerequisites || [];
  if (prerequisites.length) {
    meta.push(
      el("div", { class: "meta-line" }, [
        el("span", { class: "caption", text: "Builds on" }),
        el("span", { class: "badge-row" }, prerequisites.map((prereq) =>
          el("span", {
            class: "badge",
            text: String(prereq).replace(/_/g, " "),
          }))),
      ]),
    );
  }
  if (meta.length) card.append(el("div", { class: "objective-meta" }, meta));

  const moves = pedagogy.target_reasoning_moves || [];
  if (moves.length) {
    card.append(el("h3", { text: "What you'll practise" }));
    card.append(el("ul", {}, moves.map((move) => el("li", { text: move }))));
  }

  if ((pedagogy.transfer_goal || "").trim()) {
    card.append(el("p", { class: "small muted", text: pedagogy.transfer_goal }));
  }

  return card;
}

/**
 * The checker, rendered as an ordered list mirroring the server's check order
 * (exists, compiles, then one check per test). A "blocked" check could not run
 * yet because a dependency failed — it is deliberately distinct from a failure
 * so the learner is not blamed for a check the grader never reached.
 *
 * Returned as a document fragment so it slots next to the other result pieces.
 */
function renderChecker(checks) {
  const fragment = document.createDocumentFragment();
  if (!checks || !checks.length) return fragment;

  fragment.append(el("h3", { text: "Checker" }));
  const list = el("ul", { class: "check-list", "aria-label": "Checker results" });
  for (const check of checks) {
    const state = check.blocked ? "blocked" : check.passed ? "pass" : "fail";
    const body = [
      el("div", { class: "check-row__name", text: check.description || check.name }),
    ];
    const explanation = check.blocked
      ? (CHECK_CAUSE[check.cause] || "a previous check didn't pass")
      : state === "fail"
        ? (CHECK_CAUSE[check.cause] || "did not pass")
        : null;
    if (explanation) {
      body.push(el("div", { class: "check-row__detail", text: explanation }));
    }
    list.append(
      el("li", { class: `check-row check-row--${state}` }, [
        el("span", { class: "check-row__icon", "aria-hidden": "true", text: CHECK_ICON[state] }),
        el("span", { class: "visually-hidden", text: `${CHECK_WORD[state]}: ` }),
        el("span", { class: "check-row__body" }, body),
      ]),
    );
  }
  fragment.append(list);
  return fragment;
}

function renderResult(result) {
  const fragment = document.createDocumentFragment();
  const summary = result.summary || {};
  const passedAll = summary.all_passed;
  const failed = (summary.total || 0) - (summary.passed || 0);
  const hiddenFailing = (result.tests || []).filter(
    (t) => !t.passed && t.visibility === "hidden",
  ).length;

  fragment.append(
    el("div", { class: `verdict ${passedAll ? "verdict--pass" : "verdict--fail"}` }, [
      el("span", {
        class: "verdict__icon", "aria-hidden": "true", text: passedAll ? "✔" : "✘",
      }),
      el("span", {
        text: passedAll
          ? `All ${plural(summary.total, "test", "tests")} passed`
          : `${summary.passed} of ${summary.total} passed — ${plural(failed, "test", "tests")} failed`
            + (hiddenFailing ? ` (${plural(hiddenFailing, "test is", "tests are")} hidden)` : ""),
      }),
    ]),
  );

  // Coaching line: the whole point of running tests is knowing what to do next,
  // so it gets its own band directly under the verdict, not the dimmest style.
  if (result.next_action === "request_hint") {
    fragment.append(el("p", { class: "next-action", text:
      "Stuck? Use “Get next hint” below for guidance without spoiling the answer." }));
  } else if (result.next_action === "fix_compilation") {
    fragment.append(el("p", { class: "next-action", text:
      "Fix the compiler errors below, then run the tests again." }));
  } else if (result.next_action === "review_and_retry") {
    fragment.append(el("p", { class: "next-action", text:
      "Out of hints — compare your output against the expected values above, then try again." }));
  }

  // Compilation diagnostics are the compiler's own words about the learner's
  // code, so they are safe (and useful) to show.
  if (!result.compilation.success && result.compilation.diagnostics) {
    fragment.append(
      el("h3", { text: "Compiler output" }),
      codeBlock(result.compilation.diagnostics),
    );
  }

  // The checker is the pset-facing view; problems without one render nothing.
  fragment.append(renderChecker(result.checks));

  const tests = result.tests || [];
  if (tests.length) {
    fragment.append(el("h3", { text: "Tests" }));
    const list = el("ul", { class: "test-list" });
    for (const test of tests) {
      const hidden = test.visibility === "hidden";
      const body = [
        el("div", { class: "test-row__name" }, [
          el("span", { class: "visually-hidden",
            text: test.passed ? "Passed: " : "Failed: " }),
          el("span", { text: test.test_name }),
        ]),
      ];
      if (hidden) {
        // Hidden test detail is never sent by the API. Explain what "hidden"
        // means for the learner rather than describing what the UI withholds.
        body.push(el("div", { class: "test-row__hidden", text:
          "Hidden test — checks extra cases you can't see, so you can't tune your code to the grader." }));
      } else if (test.detail) {
        body.push(el("div", { class: "test-row__detail", text: test.detail }));
      }
      list.append(
        el("li", { class: `test-row ${test.passed ? "test-row--pass" : "test-row--fail"}` }, [
          el("span", {
            class: "test-row__icon", "aria-hidden": "true",
            text: test.passed ? "✔" : "✘",
          }),
          el("span", { class: "test-row__body" }, body),
        ]),
      );
    }
    fragment.append(list);
  }

  return fragment;
}

/**
 * Minimal, safe Markdown for problem statements.
 *
 * HTML is escaped first, so model-authored or user-authored text can never
 * inject markup. Only headings, lists, code, and bold/italic are supported.
 */
function renderMarkdown(text) {
  if (!text) return "";
  const escaped = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const lines = escaped.split("\n");
  const out = [];
  let inCode = false;
  let inList = false;

  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      closeList();
      out.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(line); continue; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      // A statement lives inside a card whose title is an h2. Map `#`->h3 and
      // never exceed h3, so the statement can never skip a level or present a
      // heading larger than the card that contains it.
      const level = Math.min(heading[1].length + 2, 3);
      out.push(`<h${level}>${heading[2]}</h${level}>`);
      continue;
    }
    const item = line.match(/^\s*[-*]\s+(.*)$/);
    if (item) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${item[1]}</li>`);
      continue;
    }
    if (!line.trim()) { closeList(); continue; }
    closeList();
    out.push(`<p>${line}</p>`);
  }
  closeList();
  if (inCode) out.push("</code></pre>");

  return out.join("\n")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/* -------------------------------------------------------------- routing */

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, ...rest] = raw.split("/");
  return { path: path || "dashboard", args: rest };
}

function setActiveNav(name) {
  for (const link of document.querySelectorAll("[data-nav]")) {
    if (link.dataset.nav === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

let renderToken = 0;
let firstRender = true;

const ROUTE_TITLE = {
  dashboard: "Dashboard",
  problems: "Problems",
  progress: "Progress",
  problem: "Problem",
};

async function render() {
  const view = $("#view");
  if (!view) return;

  const token = ++renderToken;
  const { path, args } = parseHash();

  let node;
  try {
    if (path === "problem" && args[0]) {
      setActiveNav("problems");
      node = await views.problem(decodeURIComponent(args[0]));
    } else if (path === "problems") {
      setActiveNav("problems");
      node = await views.problems();
    } else if (path === "progress") {
      setActiveNav("progress");
      node = await views.progress();
    } else {
      setActiveNav("dashboard");
      node = await views.dashboard();
    }
  } catch (error) {
    node = errorCard(error.message || String(error), null, error.status);
  }

  // A newer navigation started while this one was loading.
  if (token !== renderToken) return;

  view.replaceChildren(node);

  // Announce the route via a small dedicated status node rather than making
  // the whole view a live region (which would read the entire page aloud on
  // every navigation). On the first paint we skip the focus move so we do not
  // steal focus from the address bar.
  const announcer = $("#route-announcer");
  if (announcer) announcer.textContent = ROUTE_TITLE[path] || "CPractice";
  if (!firstRender) {
    $("#main").focus({ preventScroll: true });
  }
  firstRender = false;
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", render);
