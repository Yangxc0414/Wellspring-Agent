"""Execute a repository-mining ESE study from a frozen protocol.

This is the missing piece between "the pipeline can design an ESE study" and "the system
can run one": it takes a pre-registered protocol (sampling frame, time window, dedup, label
source, analysis plan), mines local clones of the named repositories, computes the
pre-registered statistics (Wilson interval, permutation test), and writes a result artifact
with provenance.

Boundaries:
- it creates no Claim / EA / Verdict / Signature and makes no gate decision;
- it mines only local checkouts; cloning is a separate, explicit step;
- a result artifact is exploratory evidence until a human signs the claim.
"""

import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

PROTOCOL_SCHEMA = "ese-study-protocol-0.1"
RESULT_SCHEMA = "ese-study-result-0.1"
UNIT_SOURCE_RE = re.compile(r"\.py$")
TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$")
BUGFIX_RE = re.compile(r"\b(fix|fixes|fixed|bug|issue|regression|hotfix|patch)\b", re.IGNORECASE)


class EseExecError(ValueError):
    pass


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_protocol(path):
    target = Path(path)
    if not target.is_file():
        raise EseExecError("protocol not found: " + str(target))
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EseExecError("cannot read protocol: " + str(exc))
    if not isinstance(data, dict) or str(data.get("schema") or "") != PROTOCOL_SCHEMA:
        raise EseExecError("protocol schema must be " + PROTOCOL_SCHEMA)
    for field in ("study_id", "method", "research_questions", "sampling_frame",
                  "time_window", "dedup_policy", "label_source", "analysis"):
        if not data.get(field):
            raise EseExecError("protocol needs " + field)
    if data["method"] != "repository-mining":
        raise EseExecError("this executor only runs repository-mining protocols")
    repos = (data["sampling_frame"] or {}).get("repos")
    if not isinstance(repos, list) or not repos:
        raise EseExecError("sampling_frame.repos must be a non-empty list")
    analysis = data["analysis"]
    for field in ("metric", "unit", "ci_level", "permutation"):
        if field not in analysis:
            raise EseExecError("analysis needs " + field)
    seed = (analysis["permutation"] or {}).get("seed")
    if not isinstance(seed, int):
        raise EseExecError("analysis.permutation.seed must be an integer")
    return data, _sha256_bytes(target.read_bytes())


def wilson_interval(successes, total, z=1.96):
    if total <= 0:
        return (0.0, 0.0)
    p = float(successes) / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) / total) + (z * z / (4.0 * total * total))) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _git(repo, args):
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise EseExecError("git failed in %s: %s" % (repo, result.stderr.decode("utf-8", "replace")[:200]))
    return result.stdout.decode("utf-8", "replace")


def extract_commits(repo_path, window=None):
    raw = _git(repo_path, ["log", "--no-merges", "--name-only",
                           "--pretty=format:__C__%H%x09%ad%x09%s", "--date=short"])
    commits = []
    current = None
    for line in raw.splitlines():
        if line.startswith("__C__"):
            parts = line[5:].split("\t", 2)
            if len(parts) == 3:
                current = {"sha": parts[0], "date": parts[1], "subject": parts[2], "files": []}
                commits.append(current)
        elif line.strip() and current is not None:
            current["files"].append(line.strip())
    out = []
    start = (window or {}).get("start") or ""
    end = (window or {}).get("end") or ""
    for commit in commits:
        if start and commit["date"] < start:
            continue
        if end and commit["date"] > end:
            continue
        if not any(UNIT_SOURCE_RE.search(path) for path in commit["files"]):
            continue
        commit["is_bugfix"] = bool(BUGFIX_RE.search(commit["subject"]))
        commit["touches_test"] = any(TEST_PATH_RE.search(path) for path in commit["files"])
        source_paths = [path for path in commit["files"] if UNIT_SOURCE_RE.search(path)]
        commit["production_cochange"] = any(not TEST_PATH_RE.search(path) for path in source_paths)
        count = len(commit["files"])
        commit["size_bucket"] = "1-2" if count <= 2 else ("3-5" if count <= 5 else ">5")
        out.append(commit)
    return out


def _rate(commits, predicate):
    selected = [c for c in commits if predicate(c)]
    hits = sum(1 for c in selected if c["touches_test"])
    return hits, len(selected)


def _permutation_indices(values, labels, n, seed):
    # Deterministic Fisher-Yates permutation using a small LCG: no numpy dependency.
    state = seed & 0x7FFFFFFF
    pooled = list(labels)
    out = []
    for _ in range(n):
        for i in range(len(pooled) - 1, 0, -1):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            j = state % (i + 1)
            pooled[i], pooled[j] = pooled[j], pooled[i]
        out.append(list(pooled))
    return out


def _factor_value(record, factor):
    if factor == "project":
        return record["repo"]
    if factor == "commit_size_bucket":
        return record["size_bucket"]
    if factor == "production_cochange":
        return "yes" if record["production_cochange"] else "no"
    return "unknown"


def _stratified(records, factors):
    """Within-stratum bug-fix difference plus a Mantel-Haenszel adjusted difference.

    This is the mapping from the S4 control variables to actual analysis: project, commit
    size and production-file co-change are computed per commit and used to stratify the
    bug-fix comparison. Strata with only one group contribute to the table but not to the
    adjusted estimate.
    """
    strata = []
    adjusted_numer = 0.0
    adjusted_denom = 0.0
    for factor in factors:
        grouped = {}
        for record in records:
            key = _factor_value(record, factor)
            bucket = grouped.setdefault(key, {"bug_hits": 0, "bug_total": 0, "other_hits": 0, "other_total": 0})
            if record["is_bugfix"]:
                bucket["bug_total"] += 1
                bucket["bug_hits"] += 1 if record["touches_test"] else 0
            else:
                bucket["other_total"] += 1
                bucket["other_hits"] += 1 if record["touches_test"] else 0
        for key in sorted(grouped):
            bucket = grouped[key]
            bug_rate = bucket["bug_hits"] / float(bucket["bug_total"]) if bucket["bug_total"] else 0.0
            other_rate = bucket["other_hits"] / float(bucket["other_total"]) if bucket["other_total"] else 0.0
            diff = bug_rate - other_rate
            degenerate = (
                bucket["bug_total"] > 0
                and bucket["other_total"] > 0
                and bug_rate in (0.0, 1.0)
                and other_rate in (0.0, 1.0)
            )
            strata.append({
                "factor": factor,
                "value": key,
                "bug": {"hits": bucket["bug_hits"], "total": bucket["bug_total"], "rate": round(bug_rate, 4)},
                "other": {"hits": bucket["other_hits"], "total": bucket["other_total"], "rate": round(other_rate, 4)},
                "difference": round(diff, 4),
                "degenerate": degenerate,
                "usable_for_adjustment": bool(bucket["bug_total"] and bucket["other_total"]) and not degenerate,
            })
            if bucket["bug_total"] and bucket["other_total"] and not degenerate:
                weight = bucket["bug_total"] * bucket["other_total"] / float(bucket["bug_total"] + bucket["other_total"])
                adjusted_numer += weight * diff
                adjusted_denom += weight
    return {
        "factors": list(factors),
        "strata": strata,
        "adjusted_difference": round(adjusted_numer / adjusted_denom, 4) if adjusted_denom else None,
        "method": "Mantel-Haenszel risk-difference weights over strata with both groups",
    }


def analyse(protocol, repo_paths):
    window = protocol.get("time_window") or {}
    analysis = protocol["analysis"]
    seed = int(analysis["permutation"]["seed"])
    n_perm = max(100, int(analysis["permutation"].get("n") or 1000))
    repos = []
    pooled = []
    records = []
    for name in repo_paths:
        commits = extract_commits(repo_paths[name], window)
        repos.append({
            "repo": name,
            "path": str(repo_paths[name]),
            "head": _git(repo_paths[name], ["rev-parse", "HEAD"]).strip(),
            "commits": len(commits),
            "test_cochange": sum(1 for c in commits if c["touches_test"]),
            "rate": round(sum(1 for c in commits if c["touches_test"]) / float(len(commits)), 4) if commits else 0.0,
            "ci": [round(x, 4) for x in wilson_interval(sum(1 for c in commits if c["touches_test"]), len(commits))],
        })
        for commit in commits:
            pooled.append((commit["is_bugfix"], commit["touches_test"]))
            records.append({
                "repo": name,
                "is_bugfix": commit["is_bugfix"],
                "touches_test": commit["touches_test"],
                "size_bucket": commit["size_bucket"],
                "production_cochange": commit["production_cochange"],
            })

    bug_hits, bug_total = _rate([{"touches_test": t, "is_bugfix": b} for b, t in pooled], lambda c: c["is_bugfix"])
    other_hits, other_total = _rate([{"touches_test": t, "is_bugfix": b} for b, t in pooled], lambda c: not c["is_bugfix"])
    observed = (bug_hits / float(bug_total) if bug_total else 0.0) - (other_hits / float(other_total) if other_total else 0.0)

    labels = [1 if b else 0 for b, _t in pooled]
    outcomes = [1 if t else 0 for _b, t in pooled]
    extreme = 0
    for perm in _permutation_indices(outcomes, labels, n_perm, seed):
        bug_idx = [outcomes[i] for i, label in enumerate(perm) if label]
        other_idx = [outcomes[i] for i, label in enumerate(perm) if not label]
        if not bug_idx or not other_idx:
            continue
        diff = sum(bug_idx) / float(len(bug_idx)) - sum(other_idx) / float(len(other_idx))
        if abs(diff) >= abs(observed):
            extreme += 1
    p_value = (extreme + 1.0) / (n_perm + 1.0)

    # Time split: per-repo median commit date, then early vs late within each repo.
    early = []
    late = []
    for name in repo_paths:
        commits = extract_commits(repo_paths[name], window)
        if not commits:
            continue
        dates = sorted(commit["date"] for commit in commits)
        median = dates[len(dates) // 2]
        for commit in commits:
            (early if commit["date"] <= median else late).append(commit["touches_test"])

    def _rate_of(items):
        return (sum(1 for item in items if item), len(items))

    e_hits, e_total = _rate_of(early)
    l_hits, l_total = _rate_of(late)
    e_rate = e_hits / float(e_total) if e_total else 0.0
    l_rate = l_hits / float(l_total) if l_total else 0.0
    observed_time = l_rate - e_rate
    time_labels = [0] * len(early) + [1] * len(late)
    time_outcomes = [1 if item else 0 for item in early + late]
    extreme_time = 0
    for perm in _permutation_indices(time_outcomes, time_labels, n_perm, seed + 1):
        e_idx = [time_outcomes[i] for i, label in enumerate(perm) if label == 0]
        l_idx = [time_outcomes[i] for i, label in enumerate(perm) if label == 1]
        if not e_idx or not l_idx:
            continue
        diff = sum(l_idx) / float(len(l_idx)) - sum(e_idx) / float(len(e_idx))
        if abs(diff) >= abs(observed_time):
            extreme_time += 1
    time_p = (extreme_time + 1.0) / (n_perm + 1.0)

    factors = analysis.get("stratification") or ["project", "commit_size_bucket", "production_cochange"]
    stratified = _stratified(records, factors)

    return {
        "schema": RESULT_SCHEMA,
        "stratified": stratified,
        "time_split": {
            "policy": "per-repo median commit date",
            "early": {"hits": e_hits, "total": e_total,
                      "rate": round(e_rate, 4), "ci": [round(x, 4) for x in wilson_interval(e_hits, e_total)]},
            "late": {"hits": l_hits, "total": l_total,
                     "rate": round(l_rate, 4), "ci": [round(x, 4) for x in wilson_interval(l_hits, l_total)]},
            "difference": round(observed_time, 4),
            "permutation": {"n": n_perm, "seed": seed + 1, "p_value_two_sided": round(time_p, 4)},
        },
        "study_id": protocol["study_id"],
        "method": protocol["method"],
        "research_questions": protocol["research_questions"],
        "repos": repos,
        "pooled": {
            "commits": len(pooled),
            "test_cochange": sum(outcomes),
            "rate": round(sum(outcomes) / float(len(outcomes)), 4) if outcomes else 0.0,
            "ci": [round(x, 4) for x in wilson_interval(sum(outcomes), len(outcomes))],
            "bugfix": {"hits": bug_hits, "total": bug_total,
                        "rate": round(bug_hits / float(bug_total), 4) if bug_total else 0.0},
            "non_bugfix": {"hits": other_hits, "total": other_total,
                            "rate": round(other_hits / float(other_total), 4) if other_total else 0.0},
            "difference": round(observed, 4),
            "permutation": {"n": n_perm, "seed": seed, "p_value_two_sided": round(p_value, 4)},
        },
        "boundary": (
            "exploratory repository-mining result; test/bug labels are path and message heuristics; "
            "no Claim/EA/signature, no gate decision"
        ),
    }


def run_study(protocol_path, repo_paths, output_dir):
    protocol, digest = load_protocol(protocol_path)
    result = analyse(protocol, repo_paths)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": RESULT_SCHEMA,
        "protocol_sha256": digest,
        "repos": result["repos"],
        "pooled": result["pooled"],
        "stratified": result["stratified"],
        "time_split": result["time_split"],
        "research_questions": result["research_questions"],
        "study_id": result["study_id"],
        "method": result["method"],
        "boundary": result["boundary"],
    }
    (target / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "result.md").write_text(render_markdown(payload), encoding="utf-8")
    return payload


def emit_run_artifacts(protocol_path, result, output_dir):
    """Write S5-style run artifacts (capsule + EA + metrics + contract) for one study result.

    This is the bridge the ESE exploration was missing: the executor computes rates and
    intervals; this function packages them with the frozen protocol, repository HEADs and
    code hash into the same artifact family that run-contract verification understands.
    It writes files only; signing a Claim stays a human CLI step.
    """
    from .contracts import EvidenceArtifact, RunCapsule
    from .run_contract import build_run_contract, verify_run_contract

    protocol, digest = load_protocol(protocol_path)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    run_dir = target / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = run_dir / "metrics.json"
    pooled = result.get("pooled") or {}
    seeds = [int((protocol.get("analysis") or {}).get("permutation", {}).get("seed") or 42)]
    metrics = []
    for repo in result.get("repos") or []:
        metrics.append({
            "repo": repo["repo"],
            "head": repo.get("head", ""),
            "commits": repo["commits"],
            "repo_rate": repo["rate"],
            "ci_low": repo["ci"][0],
            "ci_high": repo["ci"][1],
        })
    # A pooled row carries the claim-level metrics as identifier keys, so
    # run.verify_claim_assertions can recompute them without special-casing ESE.
    metrics.append({
        "seed": int(seeds[0]) if seeds else 42,
        "test_cochange_rate": pooled.get("rate"),
        "bugfix_difference": pooled.get("difference"),
        "adjusted_difference": (result.get("stratified") or {}).get("adjusted_difference"),
        "time_split_difference": (result.get("time_split") or {}).get("difference"),
        "pooled": True,
    })
    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    repo_heads = {repo["repo"]: repo.get("head", "") for repo in result.get("repos") or []}
    dataset_sha = _sha256_bytes(json.dumps(repo_heads, sort_keys=True).encode("utf-8"))
    code_path = Path(__file__).resolve()
    rates = [repo["rate"] for repo in result.get("repos") or []]
    mean = float(pooled.get("rate") or 0.0)
    if rates:
        avg = sum(rates) / float(len(rates))
        std = math.sqrt(sum((rate - avg) ** 2 for rate in rates) / float(len(rates)))
    else:
        std = 0.0
    seeds = [int((protocol.get("analysis") or {}).get("permutation", {}).get("seed") or 42)]
    capsule = RunCapsule(
        run_id=str(protocol.get("study_id") or "ESE-STUDY"),
        protocol_id=str(protocol.get("study_id") or ""),
        protocol_sha256=digest,
        dataset_id="msr-corpus:" + ",".join(sorted(repo_heads)),
        dataset_sha256=dataset_sha,
        code_sha256=_sha256_bytes(code_path.read_bytes()),
        model="repository-mining",
        seeds=seeds,
        test_size=0.0,
        metric_name="test_cochange_rate",
        metrics_by_seed=[{"seed": seeds[0], "test_cochange_rate": mean, "adjusted_difference": (result.get("stratified") or {}).get("adjusted_difference")}],
        mean=mean,
        std=std,
        environment={"python": "%d.%d.%d" % __import__("sys").version_info[:3]},
        status="completed",
        artifacts={"metrics": str(metrics_path), "evidence": str(evidence_path)},
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds"),
        warnings=[
            "repository-mining exploratory analysis; labels are path/message heuristics",
            "no Claim/EA signing here; S5b stays a human decision",
        ],
    )
    capsule_path = run_dir / "run-capsule.json"
    capsule_path.write_text(
        json.dumps(capsule.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ea = EvidenceArtifact(
        artifact_id="EA-" + _sha256_bytes((capsule.run_id + _sha256_bytes(evidence_path.read_bytes())).encode("utf-8"))[:12],
        kind="metric",
        run_id=capsule.run_id,
        path=str(evidence_path),
        sha256=_sha256_bytes(evidence_path.read_bytes()),
        source="ese-exec",
        captured_at=capsule.created_at,
        immutable=True,
        scope="S5/" + capsule.run_id,
    )
    ea_path = run_dir / "ea.json"
    ea_path.write_text(json.dumps(ea.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    contract = build_run_contract(protocol, None, {"capsule": capsule.__dict__})
    (run_dir / "run-contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verification = verify_run_contract(
        contract, {"capsule": capsule.__dict__, "evidence": ea.__dict__}, run_dir=run_dir
    )
    (run_dir / "run-contract-check.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "run_dir": str(run_dir),
        "capsule": str(capsule_path),
        "ea": str(ea_path),
        "metrics": str(metrics_path),
        "contract": str(run_dir / "run-contract.json"),
        "check": verification,
    }


def render_markdown(result):
    lines = [
        "# ESE study result: " + str(result["study_id"]),
        "",
        "| repo | commits | test co-change | rate | 95% CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for repo in result["repos"]:
        lines.append("| {0} | {1} | {2} | {3:.3f} | [{4:.3f}, {5:.3f}] |".format(
            repo["repo"], repo["commits"], repo["test_cochange"], repo["rate"], repo["ci"][0], repo["ci"][1]))
    pooled = result["pooled"]
    lines.extend([
        "",
        "Pooled: {0}/{1} = {2:.3f}, 95% CI [{3:.3f}, {4:.3f}]".format(
            pooled["test_cochange"], pooled["commits"], pooled["rate"], pooled["ci"][0], pooled["ci"][1]),
        "Bug-fix commits: {0}/{1} = {2:.3f}; other: {3}/{4} = {5:.3f}".format(
            pooled["bugfix"]["hits"], pooled["bugfix"]["total"], pooled["bugfix"]["rate"],
            pooled["non_bugfix"]["hits"], pooled["non_bugfix"]["total"], pooled["non_bugfix"]["rate"]),
        "Difference: {0:+.3f}; permutation p (two-sided) = {1}".format(
            pooled["difference"], pooled["permutation"]["p_value_two_sided"]),
        "",
        "Adjusted (Mantel-Haenszel) bug-fix difference: {0}".format(result["stratified"]["adjusted_difference"]),
        "",
        "Stratified difference by factor:",
        "",
        "| factor | value | bug-fix rate | other rate | difference |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row in result["stratified"]["strata"]:
        lines.append("| {0} | {1} | {2:.3f} ({3}/{4}) | {5:.3f} ({6}/{7}) | {8:+.3f} |".format(
            row["factor"], row["value"], row["bug"]["rate"], row["bug"]["hits"], row["bug"]["total"],
            row["other"]["rate"], row["other"]["hits"], row["other"]["total"], row["difference"]))
    lines.extend([
        "",
        "Time split (per-repo median date): early {0}/{1} = {2:.3f}; late {3}/{4} = {5:.3f}; difference {6:+.3f}; p={7}".format(
            result["time_split"]["early"]["hits"], result["time_split"]["early"]["total"],
            result["time_split"]["early"]["rate"], result["time_split"]["late"]["hits"],
            result["time_split"]["late"]["total"], result["time_split"]["late"]["rate"],
            result["time_split"]["difference"], result["time_split"]["permutation"]["p_value_two_sided"]),
        "",
        "> " + str(result.get("boundary")),
    ])
    return "\n".join(lines) + "\n"
