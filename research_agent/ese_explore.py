"""Agent-driven ESE exploration: question -> literature -> design -> protocol -> run -> reflection.

This is the layer the user asked for: not a flag, but the agent taking an empirical software
engineering question, grounding it in SE literature, drafting a method-compliant protocol,
executing it on real repository data, and writing a research note that states what was
learned and what the next question should be.

It composes existing pieces (pipeline artifacts, method registry, ese_exec) and writes a
note. It creates no Claim / EA / Verdict / Signature and makes no gate decision.
"""

import hashlib
import json
import re
from pathlib import Path

NOTE_SCHEMA = "ese-explore-note-0.1"
STOPWORDS = frozenset((
    "about", "after", "also", "among", "before", "between", "commits", "commit", "does",
    "from", "have", "into", "more", "other", "than", "that", "their", "there", "these",
    "they", "this", "those", "what", "when", "where", "which", "while", "with", "would",
))


def _terms(text):
    tokens = re.findall(r"[a-z][a-z0-9-]{2,}", str(text).lower())
    return set(token for token in tokens if token not in STOPWORDS)


def alignment(question, ideas):
    """How much the executed question shares vocabulary with the generated candidates.

    The first ESE exploration ran a question supplied on the command line while S2 had
    produced candidates about a different angle (test co-change). That mismatch is exactly
    what this check surfaces: the agent should execute a selected candidate, not an
    unrelated question.
    """
    question_terms = _terms(question)
    idea_terms = set()
    for idea in ideas or []:
        for key in ("title", "hypothesis", "falsification"):
            idea_terms.update(_terms(idea.get(key)))
    shared = sorted(question_terms & idea_terms)
    ratio = len(shared) / float(len(question_terms)) if question_terms else 0.0
    return {
        "question_terms": len(question_terms),
        "shared_terms": shared[:12],
        "overlap_ratio": round(ratio, 3),
        "status": "aligned" if ratio >= 0.2 else "weak",
    }
TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$")


class EseExploreError(ValueError):
    pass


def _load(path):
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EseExploreError("cannot read %s: %s" % (target.name, exc))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def draft_protocol(question, design, repos, study_id, method="repository-mining", selected_idea=None):
    """Turn a design draft plus a repository list into a method-compliant protocol.

    The protocol carries every repository-mining field the registry asks for; fields the
    design does not supply are fixed to explicit, honest defaults (not left blank).
    """
    if not question or not str(question).strip():
        raise EseExploreError("question is required")
    repo_entries = []
    for repo in repos:
        name = Path(str(repo)).name
        entry = {"name": name}
        if str(repo).startswith("http"):
            entry["url"] = str(repo)
        repo_entries.append(entry)
    if not repo_entries:
        raise EseExploreError("at least one repository is required")
    design = design or {}
    metric = str(design.get("primary_metric") or "test co-change rate")
    hypothesis = str(design.get("hypothesis") or "").strip()
    protocol = {
        "schema": "ese-study-protocol-0.1",
        "study_id": study_id,
        "method": method,
        "research_questions": [
            "RQ1: " + metric + " across the sampled repositories?",
            "RQ2: does it differ between bug-fix commits and other commits?",
            "RQ3: does it differ between earlier and later history?",
        ],
        "sampling_frame": {"repos": repo_entries},
        "project_selection": "public Python projects with a tests tree and at least 300 commits; vendored forks excluded",
        "time_window": {"start": "2000-01-01", "end": "2026-11-18"},
        "time_split": "per-repo median commit date",
        "dedup_policy": "merge commits excluded; one commit is one unit",
        "label_source": {
            "unit": "commit touching at least one .py file",
            "outcome": "same commit also touches tests/ or test_*.py or *_test.py",
            "bugfix": "commit subject matches fix/bug/issue/regression/hotfix/patch",
        },
        "license_check": "repository LICENSE checked before analysis; results stay local",
        "extraction_script": "scripts/run_ese_study.py (research_agent/ese_exec.py)",
        "analysis": {
            "metric": metric,
            "unit": "commit",
            "ci_level": 0.95,
            "permutation": {"n": 1000, "seed": 42},
            "stratification": ["project", "commit_size_bucket", "production_cochange"],
        },
        "design_hypothesis": hypothesis,
        "selected_idea": str((selected_idea or {}).get("title") or ""),
        "design_controls": list(design.get("controls") or []),
        "frozen_at": "2026-11-18",
        "boundary": "exploratory repository-mining study; labels are path/message heuristics; no Claim/EA/signature",
    }
    return protocol


def literature_summary(pipeline_dir):
    literature = _load(Path(pipeline_dir) / "literature.json")
    hits = literature.get("hits") or []
    sources = []
    for hit in hits[:8]:
        sources.append({
            "title": str(hit.get("title") or ""),
            "venue": str(hit.get("venue") or ""),
            "year": hit.get("year"),
        })
    return {
        "sources": sources,
        "span_count": len(literature.get("spans") or []),
        "fixture_mode": bool(literature.get("fixture_mode")),
    }


def ideas_summary(pipeline_dir):
    ideas = _load(Path(pipeline_dir) / "idea.json")
    out = []
    for candidate in (ideas.get("candidates") or [])[:3]:
        out.append({
            "title": str(candidate.get("title") or ""),
            "hypothesis": str(candidate.get("hypothesis") or ""),
            "falsification": str(candidate.get("falsification") or ""),
            "lens": str(candidate.get("lens") or ""),
            "evidence_refs": list(candidate.get("evidence_refs") or [])[:5],
        })
    return out


def design_summary(pipeline_dir):
    design = _load(Path(pipeline_dir) / "experiment.json")
    return {
        "hypothesis": str(design.get("hypothesis") or ""),
        "baseline": str(design.get("baseline") or ""),
        "primary_metric": str(design.get("primary_metric") or ""),
        "controls": list(design.get("controls") or []),
        "seeds": design.get("seeds"),
        "budget": str(design.get("budget") or ""),
        "status": str(design.get("status") or ""),
    }


def reflect(result, design):
    """Reflection is deterministic and states what the result does and does not support."""
    pooled = (result or {}).get("pooled") or {}
    time_split = (result or {}).get("time_split") or {}
    bullets = []
    if pooled:
        bullets.append(
            "RQ1: pooled rate %d/%d = %.3f (95%% CI [%.3f, %.3f])." % (
                pooled.get("test_cochange", 0), pooled.get("commits", 0),
                pooled.get("rate", 0.0), pooled.get("ci", [0, 0])[0], pooled.get("ci", [0, 0])[1]))
        bug = pooled.get("bugfix") or {}
        other = pooled.get("non_bugfix") or {}
        bullets.append(
            "RQ2: bug-fix %.3f vs other %.3f, difference %+0.3f, permutation p=%.4f." % (
                bug.get("rate", 0.0), other.get("rate", 0.0),
                pooled.get("difference", 0.0),
                (pooled.get("permutation") or {}).get("p_value_two_sided", 1.0)))
    if time_split:
        bullets.append(
            "RQ3: early %.3f vs late %.3f, difference %+0.3f, p=%.4f." % (
                (time_split.get("early") or {}).get("rate", 0.0),
                (time_split.get("late") or {}).get("rate", 0.0),
                time_split.get("difference", 0.0),
                (time_split.get("permutation") or {}).get("p_value_two_sided", 1.0)))
    bullets.append(
        "Does not support: causal claims, cross-language generalization, or any statement about individual developers.")
    bullets.append(
        "Labels are heuristics (path and commit-message); misclassification is expected and unquantified.")
    next_question = (
        "Next question: does the observed bug-fix difference survive when controlling for commit size "
        "and repository (stratified analysis)?"
    )
    return {"observations": bullets, "next_question": next_question}


def render_note(question, study_id, literature, ideas, design, protocol, result, reflection, protocol_path, result_path):
    lines = [
        "# ESE exploration note: " + str(question),
        "",
        "- study: " + str(study_id),
        "- protocol: " + str(protocol_path),
        "- result: " + str(result_path),
        "",
        "## 1. Literature grounding",
        "",
    ]
    if not literature.get("sources"):
        lines.append("- no SE corpus supplied; the question is not grounded in literature in this run")
    for source in literature.get("sources", []):
        lines.append("- {0} ({1}, {2})".format(source["title"], source["venue"], source["year"]))
    lines.extend(["", "Spans parsed: %d; fixture_mode: %s" % (literature.get("span_count", 0), literature.get("fixture_mode")), ""])
    lines.extend(["## 2. Candidate ideas", ""])
    if not ideas:
        lines.append("- no candidates (pipeline artifact missing)")
    for index, idea in enumerate(ideas, 1):
        lines.append("{0}. **{1}**".format(index, idea["title"]))
        lines.append("   - hypothesis: " + idea["hypothesis"][:240])
        lines.append("   - falsification: " + idea["falsification"][:240])
        lines.append("   - lens: {0}; refs: {1}".format(idea["lens"], ", ".join(idea["evidence_refs"])))
    link = reflection.get("alignment") or {}
    lines.extend(["", "## 2b. Question-idea alignment", ""])
    if link:
        lines.append("- overlap {0} with generated candidates ({1} of {2} question terms share vocabulary: {3})".format(
            link.get("overlap_ratio"), len(link.get("shared_terms") or []),
            link.get("question_terms"), ", ".join(link.get("shared_terms") or []) or "none"))
        if link.get("status") == "weak":
            lines.append("- **weak**: the executed question is not grounded in the generated candidates; "
                         "the next iteration should select an idea at G1 and derive the question from it")
    lines.extend(["", "## 3. Design draft (S4)", ""])
    for key in ("hypothesis", "baseline", "primary_metric", "controls", "seeds", "budget"):
        lines.append("- {0}: {1}".format(key, design.get(key)))
    lines.append("- status: " + str(design.get("status")))
    controls = protocol.get("design_controls") or []
    lines.extend(["", "## 3b. Design-protocol gap", ""])
    if controls:
        lines.append("- S4 controls: " + "; ".join(str(item) for item in controls))
        lines.append("- implemented in the analysis: project, commit-size bucket, production-file co-change strata, "
                     "plus the per-repo median-date split (Mantel-Haenszel adjusted difference in result.json; "
                     "degenerate strata where both groups are 0% or 100% are excluded from the adjusted estimate)")
        lines.append("- still not implemented: author identity and calendar-time buckets finer than the median split")
    else:
        lines.append("- no controls in the design draft")
    if protocol.get("selected_idea"):
        lines.append("- selected candidate: " + str(protocol.get("selected_idea")))
    lines.append("- selection is unsigned: no G1 decision is recorded; the top-ranked candidate is used as-is")
    lines.extend(["", "## 4. Protocol completeness", ""])
    missing = [field for field in ("sampling_frame", "project_selection", "time_window", "time_split",
                                    "dedup_policy", "label_source", "license_check", "extraction_script")
               if not protocol.get(field)]
    lines.append("- all eight repository-mining fields present" if not missing else "- missing: " + ", ".join(missing))
    lines.extend(["", "## 5. Executed result", ""])
    pooled = result.get("pooled") or {}
    if pooled:
        lines.append("- pooled: %d/%d = %.3f, 95%% CI [%.3f, %.3f]" % (
            pooled.get("test_cochange", 0), pooled.get("commits", 0), pooled.get("rate", 0.0),
            pooled.get("ci", [0, 0])[0], pooled.get("ci", [0, 0])[1]))
    for repo in result.get("repos") or []:
        lines.append("- {0}: {1} commits, rate {2:.3f}, CI [{3:.3f}, {4:.3f}]".format(
            repo["repo"], repo["commits"], repo["rate"], repo["ci"][0], repo["ci"][1]))
    lines.extend(["", "## 6. Reflection", ""])
    for bullet in reflection.get("observations", []):
        lines.append("- " + bullet)
    lines.append("")
    lines.append("**" + reflection.get("next_question", "") + "**")
    lines.append("")
    lines.append("> exploratory only: no Claim/EA/signature, no gate decision.")
    return "\n".join(lines) + "\n"


def run_exploration(question, pipeline_dir, repos, output_dir, study_id):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    literature = literature_summary(pipeline_dir)
    ideas = ideas_summary(pipeline_dir)
    design = design_summary(pipeline_dir)
    protocol = draft_protocol(question, design, repos, study_id, selected_idea=(ideas[0] if ideas else None))
    protocol_path = output / "protocol.json"
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from .ese_exec import run_study

    repo_paths = {Path(str(repo)).name: Path(str(repo)) for repo in repos}
    result = run_study(protocol_path, repo_paths, output)
    reflection = reflect(result, design)
    reflection["alignment"] = alignment(question, ideas)
    note = render_note(question, study_id, literature, ideas, design, protocol, result, reflection,
                       protocol_path, output / "result.json")
    note_path = output / "note.md"
    note_path.write_text(note, encoding="utf-8")
    return {
        "schema": NOTE_SCHEMA,
        "study_id": study_id,
        "question": question,
        "note": str(note_path),
        "protocol": str(protocol_path),
        "result": str(output / "result.json"),
        "pooled": result.get("pooled"),
        "reflection": reflection,
    }
