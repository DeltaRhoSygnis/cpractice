"""Phase 7.5 adversarial probe: try to make the gate accept a bad pset.

Two attacks, both attempted over the real HTTP boundary (the import path),
against a live server whose AI provider is disabled — so the gate is provably
deciding on its own, with no model in the loop:

  A. a pset whose starter already solves the problem (the learner is handed
     the answer);
  B. a pset whose concept pair sits above the learner's declared frontier
     (it assumes knowledge the learner never declared knowing).

Expected: both are REJECTED with an error-level finding, and neither package
is written to disk.

Usage:
    python3 phase7_adversarial.py <base_url>
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8124"
ROOT = Path(__file__).resolve().parent.parent

FAILURES: list[str] = []


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def step(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILURES.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def findings_of(body: dict) -> list[dict]:
    for key in ("findings", "errors", "quality", "report"):
        value = body.get(key)
        if isinstance(value, dict) and "findings" in value:
            return value["findings"]
        if isinstance(value, list):
            return value
    return body.get("findings", []) or []


def error_codes(body: dict) -> list[str]:
    return [f.get("code", "?") for f in findings_of(body)
            if f.get("severity", "error") == "error"]


def package_on_disk(problem_id: str) -> bool:
    return (ROOT / "problems" / problem_id).exists()


BASE_PACKAGE = json.loads(
    (ROOT / "problems" / "pset-vote-tally" / "problem.json").read_text()
)
# The on-disk package keeps the C sources in sibling files; the repository
# loader reads those, while the import endpoint takes the same package as one
# flat JSON document. So the import payload must carry the code inline.
BASE_PACKAGE["starter_code"] = (
    ROOT / "problems" / "pset-vote-tally" / "starter" / "main.c"
).read_text()
BASE_PACKAGE["reference_solution"] = (
    ROOT / "problems" / "pset-vote-tally" / "reference" / "main.c"
).read_text()
# Metadata lives at the TOP level of a package, not under a "metadata" key.
BASE_PACKAGE.pop("metadata", None)

print(f"Phase 7.5 adversarial probe against {BASE}\n")

# Declare the learner's checklist, so frontier legality is decidable.
status, _ = call("PUT", "/api/preferences/known-concepts", {"known_concepts": ["for_loops", "input_output"]})
step("learner checklist declared", status in (200, 204), f"status={status}")

# --- Attack A: a starter that already solves the problem --------------------
attack_a = copy.deepcopy(BASE_PACKAGE)
attack_a["id"] = "adversarial-solved-starter"
attack_a["title"] = "Adversarial: solved starter"
# The reference solution IS the answer, so the starter is a solved starter.
attack_a["starter_code"] = attack_a["reference_solution"]

status, body = call("POST", "/api/problems/import", {"package": attack_a, "overwrite": True})
codes = error_codes(body)
step("A. solved starter is REJECTED", status != 200 or bool(codes), f"status={status} codes={codes}")
step("A. rejection cites a distribution finding",
     any("starter" in c or "distribution" in c for c in codes), f"codes={codes}")
step("A. package NOT written to disk", not package_on_disk("adversarial-solved-starter"))

# --- Attack B: a concept pair above the learner's frontier -----------------
attack_b = copy.deepcopy(BASE_PACKAGE)
attack_b["id"] = "adversarial-above-frontier"
attack_b["title"] = "Adversarial: above frontier"
# The learner declared only for_loops + input_output. This pset is
# schema-valid, but it assumes pointers and structs, neither of which was
# declared known -- so it sits above the learner's frontier.
attack_b["kind"] = "problem_set"
attack_b["concept"] = {
    "new_concept": "recursion",
    "assumed_known": ["pointers", "structs"],
}

status, body = call("POST", "/api/problems/import", {"package": attack_b, "overwrite": True})
codes = error_codes(body)
step("B. above-frontier reference is REJECTED", status != 200 or bool(codes), f"status={status} codes={codes}")
step("B. rejection cites a concept-legality finding",
     any("concept" in c for c in codes), f"codes={codes}")
step("B. package NOT written to disk", not package_on_disk("adversarial-above-frontier"))

# --- Control: the unmodified pset still imports cleanly ---------------------
control = copy.deepcopy(BASE_PACKAGE)
control["id"] = "adversarial-control"
status, body = call("POST", "/api/problems/import", {"package": control, "overwrite": True})
step("control. the genuine pset still passes the gate",
     status == 200 and not error_codes(body), f"status={status} codes={error_codes(body)}")

# The control *is* accepted, so it really is written to disk. Remove it: the
# probe must leave the problems directory exactly as it found it.
shutil.rmtree(ROOT / "problems" / "adversarial-control", ignore_errors=True)
step("probe left no packages behind",
     not any((ROOT / "problems").glob("adversarial-*")),
     f"left={[p.name for p in (ROOT / 'problems').glob('adversarial-*')]}")

print()
if FAILURES:
    print(f"PROBE FAILED — {len(FAILURES)} check(s) failed: {FAILURES}")
    raise SystemExit(1)
print("PROBE PASSED — the gate rejected both attacks and accepted the control.")
