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
  // icon, exactly as the status lines do. A visually-hidden word gives screen
  // readers the same state cue, since the message itself may be terse
  // (e.g. "HTTP 500") and the icon is aria-hidden.
  const node = el("div", { class: `toast toast--${kind}` }, [
    el("span", { class: "toast__icon", "aria-hidden": "true", text: TOAST_ICON[kind] || "✔" }),
    el("span", { class: "visually-hidden", text: `${TOAST_WORD[kind] || "Notice"}: ` }),
    el("span", { text: message }),
  ]);
  region.append(node);
  setTimeout(() => node.remove(), 5000);
}

/* ------------------------------------------------------------------- api */

const api = {
  async request(method, path, body) {
    const options = { method, headers: { Accept: "application/json" } };
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
  generate: (params) => api.request("POST", "/problems/generate", params),
};

/* --------------------------------------------------------------- helpers */

const STATUS_ICON = { ok: "✔", warn: "!", fail: "✘", pending: "…" };

function statusLine(state, text) {
  return el("li", { class: `status-line status-line--${state}` }, [
    el("span", { class: "status-icon", "aria-hidden": "true", text: STATUS_ICON[state] }),
    el("span", { text }),
  ]);
}

function loading(label = "Loading…") {
  return el("div", { class: "card" }, [
    el("span", { class: "spinner", "aria-hidden": "true" }),
    el("span", { class: "muted", text: ` ${label}` }),
  ]);
}

function errorCard(message, retry) {
  const children = [
    el("h2", { text: "Something went wrong" }),
    el("p", { class: "muted", text: message }),
  ];
  if (retry) {
    children.push(el("button", { class: "secondary", text: "Retry", onclick: retry }));
  }
  return el("div", { class: "card" }, children);
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

  const statusCard = el("div", { class: "card" }, [el("h2", { text: "System status" })]);
  const statusList = el("ul", { class: "status-list" }, [
    statusLine("pending", "Checking backend…"),
  ]);
  statusCard.append(statusList);
  container.append(statusCard);

  const actionCard = el("div", { class: "card" }, [el("h2", { text: "Get a problem" })]);
  const topic = el("input", { type: "text", value: "loops", id: "gen-topic" });
  const difficulty = el("select", { id: "gen-difficulty" }, [
    el("option", { value: "beginner", text: "Beginner" }),
    el("option", { value: "intermediate", text: "Intermediate" }),
    el("option", { value: "advanced", text: "Advanced" }),
  ]);
  const generateBtn = el("button", { text: "Generate problem" });
  const generateOut = el("div");

  generateBtn.addEventListener("click", async () => {
    generateBtn.disabled = true;
    generateBtn.textContent = "Generating…";
    generateOut.replaceChildren(
      el("p", { class: "small muted" }, [
        el("span", { class: "spinner", "aria-hidden": "true" }),
        " Asking the model, then compiling and testing the reference. This can take ~30s.",
      ]),
    );
    try {
      const result = await api.generate({
        topic: topic.value.trim() || "loops",
        difficulty: difficulty.value,
      });
      if (result.accepted) {
        toast(`Generated and validated: ${result.problem_id}`, "ok");
        const ref = result.reference;
        generateOut.replaceChildren(
          el("div", { class: "verdict verdict--pass" }, [
            el("span", { class: "verdict__icon", "aria-hidden": "true", text: "✔" }),
            el("span", {
              text: `Validated — reference passes ${ref.passed}/${ref.total} tests`,
            }),
          ]),
          el("p", {}, [
            el("a", { href: `#/problem/${encodeURIComponent(result.problem_id)}`,
                      text: "Open the problem →" }),
          ]),
        );
        // The new problem changes recommendations and the problem list, so
        // refresh both rather than leaving stale content on screen.
        await Promise.all([refreshProblems(), refreshRecommendations()]);
      } else {
        generateOut.replaceChildren(
          el("div", { class: "verdict verdict--fail" }, [
            el("span", { class: "verdict__icon", "aria-hidden": "true", text: "✘" }),
            el("span", { text: "Rejected by the quality gate" }),
          ]),
          el("ul", { class: "test-list" },
            (result.errors || []).map((e) =>
              el("li", { class: "test-row" }, [
                el("span", { class: "test-row__icon", text: "!" }),
                el("span", { class: "test-row__body" }, [
                  el("div", { class: "test-row__name", text: e.code }),
                  el("div", { class: "test-row__detail", text: e.message }),
                ]),
              ]))),
        );
      }
    } catch (error) {
      generateOut.replaceChildren(errorCard(error.message));
      toast(error.message, "fail");
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate problem";
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
  container.append(actionCard);

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
        problemsCard.append(emptyState("No problems saved yet. Generate one above."));
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
                  text: problem.status,
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
  api.health().then((health) => {
    statusList.replaceChildren(
      statusLine("ok", `Backend reachable — ${health.app} v${health.version}`),
    );
    const caps = health.capabilities || {};
    const compiler = caps.compiler || {};
    const ai = caps.ai || {};
    statusList.append(
      compiler.available
        ? statusLine("ok", `C compiler available (${compiler.configured})`)
        : statusLine("warn", `C compiler missing (${compiler.configured}) — grading unavailable`),
    );
    statusList.append(
      ai.key_configured
        ? statusLine("ok", `AI provider ready (${ai.provider} / ${ai.model})`)
        : statusLine("warn", `AI key not set (${ai.provider}) — generation and hints limited`),
    );
  }).catch((error) => {
    statusList.replaceChildren(statusLine("fail", `Backend unreachable — ${error.message}`));
  });

  refreshRecommendations();
  refreshProblems();

  api.attempts(5).then((data) => {
    if (!data.count) {
      recentCard.append(emptyState("No attempts yet."));
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
      card.append(emptyState("No problems saved yet. Generate one from the dashboard."));
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
    card.append(errorCard(error.message));
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
      errorCard(error.message, () => render()),
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
          el("div", {}, [
            el("label", { text: `Input — ${test.name}` }),
            codeBlock(test.stdin || "(none)"),
          ]),
          el("div", {}, [
            el("label", { text: "Expected output" }),
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

  const submitBtn = el("button", { text: "Submit for grading" });
  const clearBtn = el("button", { class: "secondary", text: "Reset to starter" });
  clearBtn.addEventListener("click", () => {
    if (!confirm("Discard your current code and restore the starter?")) return;
    editor.value = problem.starter_code || "";
    saveDraft(problem.id, editor.value);
  });

  const resultRegion = el("div");
  let hintsUsed = 0;
  let lastFailure = "";

  editorCard.append(
    el("div", { class: "field" }, [editor]),
    el("div", { class: "button-row" }, [submitBtn, clearBtn]),
    el("p", { class: "small muted", text: "Your draft is saved in this browser." }),
    resultRegion,
  );
  container.append(editorCard);

  // --- hints ---
  const hintCard = el("div", { class: "card" }, [el("h2", { text: "Hints" })]);
  const ladder = el("div", { class: "hint-ladder", "aria-label": "Hint progress" });
  const hintOut = el("div");

  function renderLadder() {
    ladder.replaceChildren();
    const max = problem.max_hint_level || 5;
    for (let level = 1; level <= max; level++) {
      const state =
        level <= hintsUsed ? "hint-step--used" : level === hintsUsed + 1 ? "hint-step--next" : "";
      ladder.append(
        el("span", {
          class: `hint-step ${state}`,
          text: String(level),
          title: level <= hintsUsed ? `Hint ${level} used` : `Hint ${level}`,
        }),
      );
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
          `Hint ${result.level}${result.is_solution_reveal ? " — approach" : ""}` +
          `${result.source === "generated" ? " (generated)" : ""}` }),
        el("div", { text: result.text }),
      ]);
      hintOut.append(box);
      if (!result.next_level) {
        hintBtn.disabled = true;
        hintBtn.textContent = "All hints used";
      }
    } catch (error) {
      toast(error.message, "warn");
      hintOut.append(el("p", { class: "muted small", text: error.message }));
    } finally {
      hintBtn.disabled = hintBtn.disabled; // state already set above
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
  hintCard.append(
    ladder,
    el("div", { class: "button-row" }, [hintBtn, solutionBtn]),
    hintOut,
  );
  container.append(hintCard);

  // --- submit handler ---
  submitBtn.addEventListener("click", async () => {
    submitBtn.disabled = true;
    submitBtn.textContent = "Grading…";
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
      resultRegion.replaceChildren(errorCard(error.message));
      toast(error.message, "fail");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit for grading";
    }
  });

  return container;
};

/* --- progress --- */
views.progress = async () => {
  const container = el("div");
  container.append(
    el("h1", { text: "Progress" }),
    el("p", { class: "subtitle", text: "Observed results from recorded attempts." }),
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
      [rate, "Test pass rate"],
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
      summaryCard.append(el("h2", { text: "Weak topics", style: "margin-top:1rem" }));
      const list = el("ul", { class: "test-list" });
      for (const item of data.weak_topics) {
        list.append(
          el("li", { class: "test-row" }, [
            el("span", { class: "test-row__icon", text: "!" }),
            el("span", { class: "test-row__body" }, [
              el("div", { class: "test-row__name", text: (item.topics || []).join(", ") }),
              el("div", { class: "test-row__detail", text: `${item.failures} failing attempt(s)` }),
            ]),
          ]),
        );
      }
      summaryCard.append(list);
    }

    const categories = data.failure_categories || {};
    const entries = Object.entries(categories);
    if (entries.length) {
      summaryCard.append(el("h2", { text: "Failure categories", style: "margin-top:1rem" }));
      const list = el("ul", { class: "test-list" });
      for (const [category, count] of entries) {
        list.append(
          el("li", { class: "test-row" }, [
            el("span", { class: "test-row__icon", text: "•" }),
            el("span", { class: "test-row__body" }, [
              el("div", { class: "test-row__name", text: category.replace(/_/g, " ") }),
              el("div", { class: "test-row__detail", text: `${count} occurrence(s)` }),
            ]),
          ]),
        );
      }
      summaryCard.append(list);
    }
  }).catch((error) => summaryCard.append(el("p", { class: "muted", text: error.message })));

  api.attempts(25).then((data) => {
    if (!data.count) {
      attemptsCard.append(emptyState("No attempts recorded yet."));
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
          el("div", { class: "stat__label", text: "Failures" }),
        ]),
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: String(today.total_tokens || 0) }),
          el("div", { class: "stat__label", text: "Tokens" }),
        ]),
        el("div", { class: "stat" }, [
          el("div", { class: "stat__value", text: budget.unlimited ? "∞" : String(budget.remaining) }),
          el("div", { class: "stat__label", text: "Budget left" }),
        ]),
      ]),
      el("p", { class: "small muted", text: `${data.provider} / ${data.model}` }),
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
            `${attempt.verdict.replace(/_/g, " ")} · ${attempt.hints_used} hint(s) · ${attempt.created_at}` }),
        ]),
      ]),
    );
  }
  return list;
}

function renderResult(result) {
  const fragment = document.createDocumentFragment();
  const summary = result.summary || {};
  const passedAll = summary.all_passed;

  fragment.append(
    el("div", { class: `verdict ${passedAll ? "verdict--pass" : "verdict--fail"}` }, [
      el("span", {
        class: "verdict__icon", "aria-hidden": "true", text: passedAll ? "✔" : "✘",
      }),
      el("span", {
        text: passedAll
          ? `All ${summary.total} tests passed`
          : `${summary.passed} / ${summary.total} tests passed`,
      }),
    ]),
  );

  // Compilation diagnostics are the compiler's own words about the learner's
  // code, so they are safe (and useful) to show.
  if (!result.compilation.success && result.compilation.diagnostics) {
    fragment.append(
      el("h2", { text: "Compiler output", style: "font-size:.95rem;margin:.9rem 0 .3rem" }),
      codeBlock(result.compilation.diagnostics),
    );
  }

  const tests = result.tests || [];
  if (tests.length) {
    fragment.append(
      el("h2", { text: "Tests", style: "font-size:.95rem;margin:.9rem 0 .3rem" }),
    );
    const list = el("ul", { class: "test-list" });
    for (const test of tests) {
      const hidden = test.visibility === "hidden";
      const body = [
        el("div", { class: "test-row__name", text: test.test_name }),
      ];
      if (hidden) {
        // Hidden test detail is never sent by the API; say so plainly rather
        // than implying output was withheld by the UI.
        body.push(el("div", { class: "test-row__hidden", text:
          "hidden test — details are not shown" }));
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

  if (result.next_action === "request_hint") {
    fragment.append(el("p", { class: "small muted", text:
      "Stuck? Use “Get next hint” below for guidance without spoiling the answer." }));
  } else if (result.next_action === "fix_compilation") {
    fragment.append(el("p", { class: "small muted", text:
      "Fix the compiler errors above, then submit again." }));
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
      const level = heading[1].length + 2; // keep page heading hierarchy sane
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
    node = errorCard(error.message || String(error));
  }

  // A newer navigation started while this one was loading.
  if (token !== renderToken) return;

  view.replaceChildren(node);
  $("#main").focus({ preventScroll: true });
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", render);
