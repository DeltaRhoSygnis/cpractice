"use strict";

/**
 * CPractice frontend bootstrap.
 *
 * Milestone 1 only verifies that the browser can reach the backend and renders
 * the reported capabilities. Later milestones add the problem workspace.
 */

const STATUS_CLASS = {
  ok: "status-line--ok",
  warn: "status-line--warn",
  fail: "status-line--fail",
  pending: "status-line--pending",
};

const STATUS_ICON = {
  ok: "✔",
  warn: "!",
  fail: "✘",
  pending: "…",
};

/** Create a status list item. Text carries the state, not colour alone. */
function statusLine(state, text) {
  const li = document.createElement("li");
  li.className = `status-line ${STATUS_CLASS[state] ?? STATUS_CLASS.pending}`;

  const icon = document.createElement("span");
  icon.className = "status-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = STATUS_ICON[state] ?? STATUS_ICON.pending;

  const label = document.createElement("span");
  label.className = "status-text";
  label.textContent = text;

  li.append(icon, label);
  return li;
}

function renderStatus(list, health) {
  list.replaceChildren();

  list.append(statusLine("ok", `Backend reachable — ${health.app} v${health.version}`));

  const caps = health.capabilities ?? {};

  const compiler = caps.compiler ?? {};
  if (compiler.available) {
    list.append(statusLine("ok", `C compiler available (${compiler.configured})`));
  } else {
    list.append(statusLine("warn", `C compiler missing (${compiler.configured ?? "?"}) — grading unavailable`));
  }

  const ai = caps.ai ?? {};
  if (ai.key_configured) {
    list.append(statusLine("ok", `AI provider configured (${ai.provider} / ${ai.model})`));
  } else {
    list.append(statusLine("warn", `AI provider key not set (${ai.provider}) — generation unavailable`));
  }

  const storage = caps.storage ?? {};
  if (storage.problems_dir && storage.workspaces_dir) {
    list.append(statusLine("ok", "Storage directories present"));
  } else {
    list.append(statusLine("warn", "Storage directories not ready"));
  }
}

function renderError(list, message) {
  list.replaceChildren(statusLine("fail", `Backend unreachable — ${message}`));
}

async function main() {
  const list = document.getElementById("status-list");
  if (!list) return;

  try {
    const response = await fetch("/api/health", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      renderError(list, `HTTP ${response.status}`);
      return;
    }
    renderStatus(list, await response.json());
  } catch (error) {
    renderError(list, error instanceof Error ? error.message : String(error));
  }
}

document.addEventListener("DOMContentLoaded", main);
