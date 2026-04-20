#!/usr/bin/env python3
"""
Aggregate install reports from GitHub Issues into static JSON.

Reads all open issues labeled 'install-report', validates them,
computes per-component stats and pair co-failure data, then outputs
data/aggregate.json. Processed issues are closed with a comment.

Usage: python scripts/aggregate.py
Requires: GITHUB_TOKEN env var, requests library
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import requests

REPO = "Anprionsa/infinity-mod-telemetry"
API = "https://api.github.com"
MIN_REPORTS = 5  # Minimum reports before publishing per-component stats
MIN_CO_INSTALLS = 5  # Minimum co-installs for pair failure data
MIN_CORRELATION = 0.2  # Minimum co-failure correlation to publish

token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERROR: GITHUB_TOKEN not set")
    sys.exit(1)

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
}


def fetch_issues(label: str, state: str = "open") -> list[dict]:
    """Fetch all issues with a given label, handling pagination."""
    issues = []
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
    """Extract JSON from a markdown code block in an issue body."""
    if not body:
        return None
    match = re.search(r"```json\s*\n(.*?)\n\s*```", body, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def validate_report(data: dict) -> bool:
    """Basic schema validation for an install report."""
    if not isinstance(data, dict):
        return False
    if data.get("schema") != 1:
        return False
    if not isinstance(data.get("components"), list):
        return False
    if not isinstance(data.get("totalComponents"), int):
        return False
    if data.get("os") not in ("windows", "linux", "macos"):
        return False
    # Check for path separators in string fields (privacy check)
    for key in ("weiduVersion", "runnerVersion", "forgeDataDate", "id"):
        val = data.get(key, "")
        if isinstance(val, str) and ("\\" in val or "/" in val):
            return False
    return True


def validate_component(comp: dict) -> bool:
    """Validate a single component outcome."""
    return (
        isinstance(comp.get("cn"), int)
        and isinstance(comp.get("tp2"), str)
        and comp.get("outcome") in ("ok", "err", "skip", "crash")
    )


def close_issue(issue_number: int, comment: str):
    """Close an issue with a comment."""
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
        print(f"Warning: Failed to close issue #{issue_number}: {e}")


def aggregate_reports():
    """Main aggregation pipeline."""
    print("Fetching install-report issues...")
    issues = fetch_issues("install-report", state="open")
    print(f"Found {len(issues)} open install-report issues")

    reports = []
    invalid_issues = []

    for issue in issues:
        # Skip pull requests
        if "pull_request" in issue:
            continue
        data = extract_json_from_body(issue.get("body", ""))
        if data and validate_report(data):
            reports.append({"data": data, "issue": issue["number"]})
        else:
            invalid_issues.append(issue["number"])

    print(f"Valid reports: {len(reports)}, Invalid: {len(invalid_issues)}")

    # Load existing aggregate to merge with
    existing = {}
    agg_path = os.path.join(os.path.dirname(__file__), "..", "data", "aggregate.json")
    if os.path.exists(agg_path):
        with open(agg_path, "r") as f:
            existing = json.load(f)

    # Merge existing component stats
    comp_stats = defaultdict(lambda: {"installs": 0, "ok": 0, "err": 0, "skip": 0, "crash": 0, "errors": defaultdict(int)})
    for key, stats in existing.get("componentStats", {}).items():
        cs = comp_stats[key]
        cs["installs"] = stats.get("installs", 0)
        cs["ok"] = stats.get("ok", 0)
        cs["err"] = stats.get("err", 0)
        cs["skip"] = stats.get("skip", 0)
        cs["crash"] = stats.get("crash", 0)
        for err in stats.get("topErrors", []):
            cs["errors"][err] += 1

    # Track mod pairs for co-failure analysis
    pair_data = defaultdict(lambda: {"coInstalls": 0, "coFailures": 0})
    for pd in existing.get("pairFailures", []):
        pk = f"{pd['modA']}-{pd['modB']}"
        pair_data[pk]["coInstalls"] = pd.get("coInstalls", 0)
        pair_data[pk]["coFailures"] = pd.get("coFailures", 0)

    # Preset popularity
    preset_counts = defaultdict(int)
    for ps in existing.get("popularSelections", []):
        preset_counts[ps.get("presetId") or "custom"] = ps.get("count", 0)

    # Engine limit samples
    kit_samples = []
    splstate_samples = []

    existing_report_count = existing.get("reportCount", 0)

    # Process new reports
    for report_entry in reports:
        data = report_entry["data"]
        components = [c for c in data.get("components", []) if validate_component(c)]

        # Per-component stats
        for comp in components:
            key = f"{comp['modId']}-{comp['ci']}"
            if comp["modId"] == -1:
                continue  # Skip unmatched components
            cs = comp_stats[key]
            cs["installs"] += 1
            outcome = comp["outcome"]
            if outcome in cs:
                cs[outcome] += 1
            if comp.get("errorPattern"):
                cs["errors"][comp["errorPattern"]] += 1

        # Pair co-failure: find all mods with errors
        failed_mods = set()
        installed_mods = set()
        for comp in components:
            if comp["modId"] == -1:
                continue
            installed_mods.add(comp["modId"])
            if comp["outcome"] in ("err", "crash"):
                failed_mods.add(comp["modId"])

        # For every pair of installed mods where at least one failed
        for mod_a in installed_mods:
            for mod_b in installed_mods:
                if mod_a >= mod_b:
                    continue
                pk = f"{mod_a}-{mod_b}"
                pair_data[pk]["coInstalls"] += 1
                if mod_a in failed_mods or mod_b in failed_mods:
                    pair_data[pk]["coFailures"] += 1

        # Preset tracking
        preset_id = data.get("presetId") or "custom"
        preset_counts[preset_id] += 1

        # Engine limits
        limits = data.get("engineLimits")
        if limits and isinstance(limits, dict):
            if "kits" in limits:
                kit_samples.append(limits["kits"])
            if "splstates" in limits:
                splstate_samples.append(limits["splstates"])

    # Build output
    output_comp_stats = {}
    for key, cs in comp_stats.items():
        if cs["installs"] < MIN_REPORTS:
            continue
        top_errors = sorted(cs["errors"].items(), key=lambda x: -x[1])[:3]
        output_comp_stats[key] = {
            "installs": cs["installs"],
            "ok": cs["ok"],
            "err": cs["err"],
            "skip": cs["skip"],
            "crash": cs["crash"],
            "failRate": round(cs["err"] / cs["installs"], 3) if cs["installs"] > 0 else 0,
            "topErrors": [e[0] for e in top_errors],
        }

    output_pairs = []
    for pk, pd in pair_data.items():
        if pd["coInstalls"] < MIN_CO_INSTALLS:
            continue
        correlation = pd["coFailures"] / pd["coInstalls"] if pd["coInstalls"] > 0 else 0
        if correlation < MIN_CORRELATION:
            continue
        mod_a, mod_b = pk.split("-")
        output_pairs.append({
            "modA": int(mod_a),
            "modB": int(mod_b),
            "coInstalls": pd["coInstalls"],
            "coFailures": pd["coFailures"],
            "correlation": round(correlation, 3),
        })
    output_pairs.sort(key=lambda x: -x["correlation"])

    def percentiles(samples):
        if not samples:
            return {"p50": 0, "p90": 0, "p99": 0, "max": 0}
        s = sorted(samples)
        n = len(s)
        return {
            "p50": s[n // 2],
            "p90": s[int(n * 0.9)],
            "p99": s[int(n * 0.99)],
            "max": s[-1],
        }

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "reportCount": existing_report_count + len(reports),
        "componentStats": output_comp_stats,
        "pairFailures": output_pairs,
        "popularSelections": [
            {"presetId": k if k != "custom" else None, "count": v}
            for k, v in sorted(preset_counts.items(), key=lambda x: -x[1])
        ],
        "engineLimits": {
            "kits": percentiles(kit_samples),
            "splstates": percentiles(splstate_samples),
        },
    }

    # Write output
    os.makedirs(os.path.dirname(agg_path), exist_ok=True)
    with open(agg_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote aggregate.json: {len(output_comp_stats)} components, {len(output_pairs)} pairs")

    # Close processed issues
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for report_entry in reports:
        close_issue(
            report_entry["issue"],
            f"Included in aggregation run {now}. Thank you for contributing!"
        )
    print(f"Closed {len(reports)} processed issues")

    # Close invalid issues with explanation
    for issue_num in invalid_issues:
        close_issue(
            issue_num,
            "This issue could not be parsed as a valid install report (schema validation failed). "
            "Please submit reports via Infinity Mod Runner's 'Share Report on GitHub' button."
        )
    if invalid_issues:
        print(f"Closed {len(invalid_issues)} invalid issues")


def _parse_version(v):
    """Parse a semver-ish version like '1.2.3' into a tuple for comparison.
    Unknown/missing versions sort lowest. Extra segments are kept for stability."""
    if not v or not isinstance(v, str):
        return (0, 0, 0)
    parts = []
    for p in v.split(".", 3):
        try:
            parts.append(int(p))
        except ValueError:
            # Strip non-numeric suffix (e.g., "1.0.0-beta" -> 0 for that segment)
            digits = "".join(c for c in p if c.isdigit())
            parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def aggregate_builds():
    """Process approved community builds into data/builds/{id}.json.

    Supports versioned updates:
      - When multiple approved issues share an id, the one with the highest
        `version` wins (tiebreak: newest `updatedAt`, then newest `createdAt`).
      - Ownership check: if an existing build on disk has an `authorGitHub`,
        incoming submissions for that id must have a matching `authorGitHub`
        (set automatically from the issue's GitHub author). Non-matching
        submissions are skipped to prevent build-id hijacking.
      - First-time submissions auto-populate `authorGitHub` from the issue user.
    """
    print("Fetching approved community-build issues...")
    # Fetch issues with BOTH labels: community-build AND approved
    all_build_issues = fetch_issues("community-build", state="all")
    approved = [
        issue for issue in all_build_issues
        if any(label.get("name") == "approved" for label in issue.get("labels", []))
        and not any(label.get("name") == "yanked" for label in issue.get("labels", []))
        and "pull_request" not in issue
    ]
    print(f"Found {len(approved)} approved (non-yanked) community builds")

    builds_dir = os.path.join(os.path.dirname(__file__), "..", "data", "builds")
    os.makedirs(builds_dir, exist_ok=True)

    # Load existing builds on disk so we can enforce ownership checks
    existing_by_id = {}
    for fname in os.listdir(builds_dir):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        try:
            with open(os.path.join(builds_dir, fname), "r") as f:
                b = json.load(f)
            existing_by_id[b.get("id", fname[:-5])] = b
        except (OSError, json.JSONDecodeError):
            continue

    # Collect candidate builds from issues, grouped by id
    candidates_by_id = {}
    for issue in approved:
        data = extract_json_from_body(issue.get("body", ""))
        if not data or data.get("schema") != 1:
            continue
        if not isinstance(data.get("keys"), list) or not data.get("name"):
            continue

        bid = data.get("id", f"issue-{issue['number']}")
        issue_author = (issue.get("user") or {}).get("login", "")
        submitted_author_gh = data.get("authorGitHub") or issue_author

        # Ownership check: incoming update must match original author's GitHub username.
        # First-time submissions (no existing build) are always accepted.
        existing = existing_by_id.get(bid)
        if existing:
            original_author = existing.get("authorGitHub")
            if original_author and original_author.lower() != (submitted_author_gh or "").lower():
                print(f"  SKIP issue #{issue['number']} for id='{bid}': author '{submitted_author_gh}' "
                      f"does not match original '{original_author}'")
                continue

        # Sanitize: ensure no unexpected fields leak through.
        # schemaVersion describes the key format: 1 = idx-based (legacy),
        # 2 = wc-based (stable across mod updates). Default 1 when absent.
        build = {
            "id": bid,
            "schema": 1,
            "schemaVersion": data.get("schemaVersion", 1),
            "version": data.get("version", "1.0.0"),
            "name": data["name"],
            "desc": data.get("desc", ""),
            "author": data.get("author", "Anonymous"),
            "authorGitHub": submitted_author_gh,
            "icon": data.get("icon", ""),
            "color": data.get("color", "#a78bfa"),
            "keys": data["keys"],
            "tier": data.get("tier"),
            "difficulty": data.get("difficulty"),
            "focus": data.get("focus", []),
            "modCount": data.get("modCount", len(set(k.split("-")[0] for k in data["keys"] if "-" in k))),
            "componentCount": data.get("componentCount", len(data["keys"])),
            "forgeVersion": data.get("forgeVersion", "unknown"),
            "createdAt": data.get("createdAt", issue.get("created_at", "")),
            "updatedAt": data.get("updatedAt", issue.get("updated_at", issue.get("created_at", ""))),
            "issueNumber": issue["number"],
        }
        candidates_by_id.setdefault(bid, []).append(build)

    # For each id, pick the winning candidate (highest version, newest updatedAt, newest createdAt).
    # This fixes the "older overwrites newer" bug from the single-pass write loop.
    builds = []
    for bid, group in candidates_by_id.items():
        group.sort(key=lambda b: (
            _parse_version(b.get("version", "0.0.0")),
            b.get("updatedAt", ""),
            b.get("createdAt", ""),
        ), reverse=True)
        winner = group[0]
        builds.append(winner)
        if len(group) > 1:
            other_versions = [b["version"] for b in group[1:]]
            print(f"  id='{bid}' version={winner['version']} wins over {other_versions}")

    # Sort final list for stable output ordering (newest updatedAt first)
    builds.sort(key=lambda b: (b.get("updatedAt", ""), b.get("createdAt", "")), reverse=True)

    # Write individual build files for each approved issue-derived build
    issue_ids = set()
    for build in builds:
        bid = build["id"]
        issue_ids.add(bid)
        with open(os.path.join(builds_dir, f"{bid}.json"), "w") as f:
            json.dump(build, f, indent=2)

    # Build index from ALL build files on disk (issue-derived + seeded).
    # This preserves hand-curated seed builds (mod-forge-ultimate, xplat-story, etc.)
    # that aren't backed by a GitHub issue.
    index = []
    for fname in sorted(os.listdir(builds_dir)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        try:
            with open(os.path.join(builds_dir, fname), "r") as f:
                build = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: skipped malformed build file {fname}: {e}")
            continue
        index.append({k: v for k, v in build.items() if k != "keys"})

    # Preserve newest-first order: sort by createdAt desc (matches the pre-split behavior).
    index.sort(key=lambda b: b.get("createdAt", ""), reverse=True)

    with open(os.path.join(builds_dir, "_index.json"), "w") as f:
        json.dump(index, f, indent=2)
    print(f"Wrote {len(builds)} issue-derived build files; _index.json lists {len(index)} total builds ({len(index) - len(issue_ids)} seeded)")


if __name__ == "__main__":
    aggregate_reports()
    aggregate_builds()
