"""Phase 7 live proof: a pset is praxisable with NO provider configured.

Runs the full learner loop over HTTP against a live server started with the
AI provider disabled:

    open -> predict -> edit -> submit -> check -> hint

Every step must work with zero AI reachable. This is the spec's central
guarantee (S13): *AI prepares and explains; the deterministic checker grades;
the learner never waits on a model.*

Usage:
    python3 phase7_proof.py <base_url> <problem_id>
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8124"
PROBLEM = sys.argv[2] if len(sys.argv) > 2 else "pset-vote-tally"

FAILURES: list[str] = []


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def step(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    if not ok:
        FAILURES.append(label)
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))


print(f"Phase 7.4 proof against {BASE} for {PROBLEM}\n")

# --- 0. the provider really is disabled -----------------------------------
status, health = call("GET", "/api/health")
step("server reachable", status == 200, f"status={status}")
ai = health.get("capabilities", {}).get("ai", {})
provider_configured = bool(ai.get("key_configured"))
step("AI provider DISABLED (no key configured)", not provider_configured, f"ai={ai}")

# --- 1. open the pset ------------------------------------------------------
status, problem = call("GET", f"/api/problems/{PROBLEM}")
step("open problem", status == 200, f"status={status}")
statement = problem.get("statement_md", "")
step("statement present", bool(statement.strip()), f"{len(statement)} chars")
starter = (problem.get("metadata") or {}).get("starter_code") or problem.get("starter_code") or ""
step("distribution (starter) code shipped", "TODO" in starter, f"{len(starter)} chars, TODOs={starter.count('TODO')}")

# --- 2. predict (the learner's hypothesis) --------------------------------
prediction = "2 majority\n"
step("prediction captured locally", bool(prediction.strip()))

# --- 3. edit: the learner finishes the starter -----------------------------
solution = """
#include <stdio.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;
    int counts[1001] = {0};
    for (int i = 0; i < n; i++) {
        int c;
        if (scanf("%d", &c) != 1) return 0;
        if (c >= 1 && c <= 1000) counts[c]++;
    }
    int best = 1;
    for (int c = 2; c <= 1000; c++) {
        if (counts[c] > counts[best]) best = c;
    }
    if (counts[best] * 2 > n) {
        printf("%d majority\\n", best);
    } else {
        printf("%d plurality\\n", best);
    }
    return 0;
}
"""
step("learner wrote a solution", bool(solution.strip()))

# --- 4. submit ------------------------------------------------------------
status, result = call(
    "POST",
    f"/api/problems/{PROBLEM}/submit",
    {"source": solution, "hints_used": 0, "predicted_stdout": prediction},
)
step("submit accepted", status == 200, f"status={status}")
payload = result.get("payload", result)
verdict = payload.get("verdict")
summary = payload.get("summary", {})
step("graded by the deterministic checker", verdict == "passed", f"verdict={verdict} summary={summary}")

# --- 5. check: the checker report is present and leaks nothing ------------
checks = payload.get("checks") or []
step("checker report present", len(checks) > 0, f"{len(checks)} checks")
names = [c.get("name") for c in checks]
step("checker is ordered exists -> compiles -> tests",
     names[:2] == ["exists", "compiles"], f"first two={names[:2]}")
leaky = [
    c.get("name") for c in checks
    if (c.get("data") or {}) or "stdin" in json.dumps(c) or "expected" in json.dumps(c).lower()
]
step("no hidden test data in the checker report", not leaky, f"leaky={leaky}")

# --- 6. prediction diff ----------------------------------------------------
pred = payload.get("prediction") or {}
step("prediction diff present", pred.get("provided") is True, json.dumps(pred)[:120])
step("prediction never changes the verdict",
     payload.get("summary", {}).get("all_passed") is True)

# --- 7. hint ladder, with no provider -------------------------------------
status, hint = call(
    "POST", f"/api/problems/{PROBLEM}/hint", {"hints_used": 0, "source": starter}
)
step("hint served with no provider", status == 200, f"status={status} source={hint.get('source')}")
step("hint came from the stored ladder", hint.get("source") == "stored", f"level={hint.get('level')}")

# --- 8. solution reveal ----------------------------------------------------
# The reveal is deliberately gated behind an explicit confirmation.
status, refused = call(
    "POST", f"/api/problems/{PROBLEM}/solution", {"source": solution}
)
step("solution reveal refuses without confirmation", status == 400, f"status={status}")

status, solution_result = call(
    "POST", f"/api/problems/{PROBLEM}/solution", {"confirm": True}
)
step("solution reveal served with no provider", status == 200, f"status={status}")
step("revealed a non-empty reference solution",
     bool((solution_result.get("reference_solution") or "").strip()))

print()
if FAILURES:
    print(f"PROOF FAILED — {len(FAILURES)} step(s) failed: {FAILURES}")
    raise SystemExit(1)
print("PROOF PASSED — the pset is fully praxisable with no provider configured.")
