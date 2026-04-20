#!/usr/bin/env python3
"""
Aggregate install traces from GitHub Issues into per-(mod, cn) baselines.

Reads all open issues labeled 'install-trace', validates them, normalizes
per-user-rig durations back to the reference rig using accelerator
discount coefficients, then emits a per-(mod, cn) aggregate file:

    data/install-traces-aggregate.json

That file is intended to be consumed by the infinity-mod-forge repo's
`scripts/trace_to_baselines.js` to patch `data/mods/*.json` with updated
`installProfile.baselineSec` / `sampleCount`. Two-stage flow keeps this
repo cheap (never has to checkout Forge or push cross-repo).

Processed issues are closed with a comment, same pattern as aggregate.py.

Usage: python scripts/aggregate_traces.py
Env:   GITHUB_TOKEN
"""

import json
import math
import os
import re
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

import requests

REPO = "Anprionsa/infinity-mod-telemetry"
FORGE_ACCELERATOR_URL = (
    "https://anprionsa.github.io/infinity-mod-forge/data/accelerator-profile-ref.json"
)
API = "https://api.github.com"
MIN_SAMPLES_TO_PUBLISH = 3

token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERROR: GITHUB_TOKEN not set")
    sys.exit(1)

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
}


# ─── Accelerator discount math (mirrors install-baselines.ts) ───


def fetch_accelerator_coefficients() -> dict:
    """Pull Forge's accelerator profile so we can normalize traces back to
    the reference rig. Falls back to placeholder constants if the fetch
    fails — matches the Runner's FALLBACK_ACCELERATOR_COEFFICIENTS."""
    try:
        with urllib.request.urlopen(FORGE_ACCELERATOR_URL, timeout=10) as resp:
            data = json.loads(resp.read())
            coeffs = data.get("coefficients") or {}
    except Exception as e:  # noqa: BLE001
        print(f"warn: fetching accelerator profile failed ({e}); using fallback")
        coeffs = {}

    return {
        "overrideFastDrive": coeffs.get(
            "overrideFastDrive", {"light": 1.0, "medium": 0.75, "heavy": 0.35}
        ),
        "experimentalWeidu": coeffs.get(
            "experimentalWeidu", {"light": 0.92, "medium": 0.90, "heavy": 0.88}
        ),
        "batchSizePenaltyPerStepBelow25": coeffs.get(
            "batchSizePenaltyPerStepBelow25", 0.006
        ),
    }


def classify(sec: float) -> str:
    if sec <= 10:
        return "light"
    if sec <= 120:
        return "medium"
    return "heavy"


def discount(cls: str, accel: dict, coeffs: dict) -> float:
    d = 1.0
    if accel.get("overrideFastDrive"):
        fd = coeffs["overrideFastDrive"]
        if cls in fd:
            d *= fd[cls]
    if accel.get("experimentalWeidu"):
        ew = coeffs["experimentalWeidu"]
        if cls in ew:
            d *= ew[cls]
    batch_size = int(accel.get("batchSize", 25))
    if cls == "light" and batch_size < 25:
        d *= 1 + (25 - batch_size) * coeffs["batchSizePenaltyPerStepBelow25"]
    return d


# ─── Issue intake (mirrors aggregate.py patterns) ───


def fetch_issues(label: str, state: str = "open") -> list[dict]:
    issues: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"{API}/repos/{REPO}/issues",
            headers=headers,
            params={"labels": label, "state": state, "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        issues.extend(batch)
        page += 1
    return issues


def extract_json_from_body(body: str) -> dict | None:
    if not body:
        return None
    match = re.search(r"```json\s*\n(.*?)\n\s*```", body, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def validate_trace(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("schema") != 1:
        return False
    if data.get("event") != "install_trace":
        return False
    if not isinstance(data.get("entries"), list):
        return False
    if not isinstance(data.get("accelerators"), dict):
        return False
    # privacy: reject any path-ish strings
    for key in ("weiduVersion", "runnerVersion", "id"):
        val = data.get(key, "")
        if isinstance(val, str) and ("\\" in val or "/" in val):
            return False
    return True


def close_issue(issue_number: int, comment: str) -> None:
    try:
        requests.post(
            f"{API}/repos/{REPO}/issues/{issue_number}/comments",
            headers=headers,
            json={"body": comment},
        ).raise_for_status()
        requests.patch(
            f"{API}/repos/{REPO}/issues/{issue_number}",
            headers=headers,
            json={"state": "closed"},
        ).raise_for_status()
    except requests.RequestException as e:
        print(f"warn: failed to close issue #{issue_number}: {e}")


# ─── Aggregation pipeline ───


def main() -> int:
    coeffs = fetch_accelerator_coefficients()

    print("Fetching install-trace issues...")
    issues = fetch_issues("install-trace", state="open")
    print(f"Found {len(issues)} open install-trace issues")

    # key: "mod:cn" → list[normalized_sec]
    samples: dict[str, list[float]] = defaultdict(list)
    valid_issue_numbers: list[int] = []
    invalid_issue_numbers: list[int] = []

    for issue in issues:
        if "pull_request" in issue:
            continue
        data = extract_json_from_body(issue.get("body", ""))
        if not data or not validate_trace(data):
            invalid_issue_numbers.append(issue["number"])
            continue
        accel = data.get("accelerators") or {}
        for entry in data.get("entries", []):
            sec = entry.get("sec")
            if not isinstance(sec, (int, float)) or sec <= 0:
                continue
            mod = str(entry.get("mod", "")).lower()
            cn = entry.get("cn")
            if not mod or not isinstance(cn, int):
                continue
            cls = classify(sec)
            d = discount(cls, accel, coeffs)
            # Divide to recover the reference-rig-equivalent duration —
            # a faster accelerator gave the user a DISCOUNTED sec, so we
            # inflate it back to baseline.
            normalized = sec / max(0.05, d)
            samples[f"{mod}:{cn}"].append(normalized)
        valid_issue_numbers.append(issue["number"])

    print(
        f"Traces parsed: valid={len(valid_issue_numbers)}, invalid={len(invalid_issue_numbers)}, "
        f"distinct (mod,cn)={len(samples)}"
    )

    # Merge with existing aggregate (if present) so we accumulate across weekly runs.
    agg_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "install-traces-aggregate.json"
    )
    existing: dict = {}
    if os.path.exists(agg_path):
        try:
            with open(agg_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"warn: couldn't load existing aggregate: {e}")

    existing_entries: dict[str, dict] = existing.get("entries", {})

    out_entries: dict[str, dict] = {}
    for key, new_samples in samples.items():
        old = existing_entries.get(key, {})
        old_count = int(old.get("sampleCount", 0))
        old_p50 = old.get("baselineSec")
        new_p50 = statistics.median(new_samples) if new_samples else None
        total = old_count + len(new_samples)
        if new_p50 is None:
            blended = old_p50
        elif old_p50 is not None and old_count > 0:
            blended = (old_p50 * old_count + new_p50 * len(new_samples)) / total
        else:
            blended = new_p50
        if blended is None:
            continue
        cls = classify(blended)
        out_entries[key] = {
            "baselineSec": round(blended * 10) / 10,
            "heavyClass": cls,
            "sampleCount": total,
            "updatedAt": datetime.now(timezone.utc).date().isoformat(),
        }

    # Preserve entries we didn't touch this run (no new samples arrived).
    for key, old in existing_entries.items():
        if key not in out_entries:
            out_entries[key] = old

    # Filter the PUBLISHED set by min-samples confidence gate. Keeping full
    # accumulator separately would double the file; for now just gate at
    # write time and recompute from issue history on future runs.
    published = {
        k: v for k, v in out_entries.items() if v.get("sampleCount", 0) >= MIN_SAMPLES_TO_PUBLISH
    }

    os.makedirs(os.path.dirname(agg_path), exist_ok=True)
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema": 1,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "totalSamples": sum(len(v) for v in samples.values()),
                "entriesPublished": len(published),
                "entriesBelowGate": len(out_entries) - len(published),
                "minSamplesToPublish": MIN_SAMPLES_TO_PUBLISH,
                "entries": published,
            },
            f,
            indent=2,
        )
    print(
        f"Wrote {agg_path}: published={len(published)} "
        f"below-gate={len(out_entries) - len(published)}"
    )

    # Close processed issues with a brief status comment.
    closed = 0
    for num in valid_issue_numbers:
        close_issue(
            num,
            "Trace ingested. Aggregated data is at "
            "[`data/install-traces-aggregate.json`](../blob/main/data/install-traces-aggregate.json). "
            "Thanks for contributing!",
        )
        closed += 1
    for num in invalid_issue_numbers:
        close_issue(
            num,
            "Could not parse this issue as a schema-1 `install_trace` payload. "
            "If this was intentional, please reopen with a corrected JSON block.",
        )
    print(f"Closed {closed} valid + {len(invalid_issue_numbers)} invalid issues.")

    return 0 if (closed or len(existing_entries)) else 1


if __name__ == "__main__":
    sys.exit(main())
