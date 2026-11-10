"""Write a consolidated summary for the top-conference article run."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.storage import write_json_atomic
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import load_writing_pack

PROJECT = ROOT / "runtime_data" / "topconf-research-2026"
RUN = "RUN-20261026T122616Z-a13294"
FINAL = PROJECT / "runs" / RUN / "manuscript-review-v4" / "final.md"
REVIEW = PROJECT / "runs" / RUN / "manuscript-review-v4" / "manuscript-review.json"
INNOVATION = PROJECT / "runs" / RUN / "innovation-review.json"
EXPORT = PROJECT / "revisions" / "REV-20261026T1601140000-f589ae" / "export"


def main() -> int:
    corpus = json.loads((PROJECT / "inputs" / "conference-corpus.json").read_text(encoding="utf-8"))
    ledger = json.loads((PROJECT / "runs" / RUN / "literature-ledger.json").read_text(encoding="utf-8"))
    task = json.loads((PROJECT / "runs" / RUN / "task.json").read_text(encoding="utf-8"))
    span_detail = next(
        (item.get("detail") for item in task.get("checks") or [] if item.get("name") == "locatable_spans"),
        "",
    )
    pack = load_writing_pack(PROJECT, RUN) or {}
    innovation = json.loads(INNOVATION.read_text(encoding="utf-8"))
    synthesis = json.loads((PROJECT / "runs" / RUN / "synthesis-matrix.json").read_text(encoding="utf-8"))
    loop = json.loads((PROJECT / "runs" / RUN / "research-loop.json").read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    final_audit = audit_manuscript(FINAL, pack=pack)
    initial = review.get("baseline_audit") or {}
    summary = {
        "schema_version": "topconf-article-final-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": str(PROJECT),
        "run_id": RUN,
        "corpus": {
            "retrieved": corpus.get("downloaded_count"),
            "per_venue": corpus.get("per_venue"),
            "years": corpus.get("years"),
            "full_text_sources": (ledger.get("counts") or {}).get("included_full_text"),
            "locatable_span_sources": (ledger.get("counts") or {}).get("with_locatable_span"),
            "total_spans": span_detail,
        },
        "writing_pack": {
            "references": len((pack.get("literature") or {}).get("references") or []),
            "token_estimate": pack.get("token_estimate"),
            "corpus": (pack.get("literature") or {}).get("corpus"),
        },
        "synthesis": {
            "theme_count": synthesis.get("theme_count"),
            "source_count": synthesis.get("source_count"),
            "unused_sources": len(synthesis.get("unused_sources") or []),
            "themes": [
                {
                    "theme_id": item.get("theme_id"),
                    "name": item.get("name"),
                    "source_count": item.get("source_count"),
                    "tension": item.get("tension"),
                }
                for item in synthesis.get("themes") or []
            ],
        },
        "loop": {
            "mode": loop.get("mode"),
            "stages": loop.get("stages"),
            "gates": loop.get("gates"),
            "iterations": loop.get("iterations"),
        },
        "innovation": {
            "status": innovation.get("status"),
            "rounds_completed": innovation.get("rounds_completed"),
            "score_progression": [item.get("overall") for item in innovation.get("iterations") or []],
            "gaps": len(innovation.get("gaps") or []),
            "selected": [
                {
                    "idea_id": item.get("idea_id"),
                    "title": item.get("title"),
                    "falsification": item.get("falsification"),
                    "evidence_refs": item.get("evidence_refs"),
                }
                for item in innovation.get("selected_ideas") or []
            ],
        },
        "manuscript": {
            "initial_audit": {
                "status": initial.get("status"),
                "blockers": initial.get("blockers"),
                "citation_count": initial.get("citation_count"),
            },
            "review_status": review.get("status"),
            "review_scores": review.get("score_progression"),
            "best_score": review.get("best_score"),
            "improved": review.get("improved"),
            "accepted_revisions": review.get("accepted_revisions"),
            "final_audit": {
                "status": final_audit.get("status"),
                "blockers": final_audit.get("blockers"),
                "citation_count": final_audit.get("citation_count"),
                "reference_count": final_audit.get("reference_count"),
                "result_number_count": final_audit.get("result_number_count"),
            },
            "final_markdown": str(FINAL),
            "export": {
                "markdown": str(EXPORT / "manuscript.md"),
                "docx": str(EXPORT / "manuscript.docx"),
                "pdf": str(EXPORT / "manuscript.pdf"),
            },
        },
        "comparison": {
            "baseline": "单次生成 + 确定性审计",
            "iterative": "创新三评审 + 初稿 + 多轮手稿评审/修订",
            "baseline_score": (review.get("score_progression") or [None])[0],
            "final_score": review.get("best_score"),
            "score_delta": round(
                (review.get("best_score") or 0) - ((review.get("score_progression") or [0])[0] or 0), 2
            ),
            "audit_preserved": final_audit.get("status") == "ready_for_human_review",
            "note": (
                "模型评审分数从 6.0 提升到 6.2，仍未达到内部 7.0 阈值；"
                "最终稿的主要改进是证据强度表、语料筛选记录、venue 未核验说明与结构一致性。"
            ),
        },
        "boundary": (
            "Position/review article, not an empirical result paper. No Claim/EA/gate/signature. "
            "Venue/year comes from arXiv comments and is not independently verified. "
            "Model review is not peer review; submission_ready is false."
        ),
    }
    write_json_atomic(PROJECT / "run-summary.json", summary)
    lines = [
        "# Top-Conference Article Run",
        "",
        "- run: `%s`" % RUN,
        "- corpus: %s 篇检索，%s 篇全文，%s 篇有可定位 span，总计 %s"
        % (summary["corpus"]["retrieved"], summary["corpus"]["full_text_sources"], summary["corpus"]["locatable_span_sources"], summary["corpus"]["total_spans"]),
        "- writing pack: %s refs, ~%s tokens" % (summary["writing_pack"]["references"], summary["writing_pack"]["token_estimate"]),
        "- loop: mode=%s; stages=%s; gates=%s"
        % (
            summary["loop"]["mode"],
            ", ".join("%s:%s" % (s["stage_id"], s["status"]) for s in summary["loop"]["stages"]),
            ", ".join("%s:%s" % (g["gate"], g["status"]) for g in summary["loop"]["gates"]),
        ),
        "- synthesis: %s themes, %s sources, %s unused"
        % (summary["synthesis"]["theme_count"], summary["synthesis"]["source_count"], summary["synthesis"]["unused_sources"]),
        "- innovation: %s rounds, %s gaps, %s selected, status `%s`"
        % (summary["innovation"]["rounds_completed"], summary["innovation"]["gaps"], len(summary["innovation"]["selected"]), summary["innovation"]["status"]),
        "- innovation scores: %s" % summary["innovation"]["score_progression"],
        "- manuscript review: %s -> best %s (improved=%s, accepted revisions=%s)"
        % (summary["manuscript"]["review_scores"], summary["manuscript"]["best_score"], summary["manuscript"]["improved"], summary["manuscript"]["accepted_revisions"]),
        "- final audit: `%s`, %s citations, %s refs (%s distinct in body), %s result numbers"
        % (summary["manuscript"]["final_audit"]["status"], summary["manuscript"]["final_audit"]["citation_count"], summary["manuscript"]["final_audit"]["reference_count"], final_audit.get("distinct_reference_count"), summary["manuscript"]["final_audit"]["result_number_count"]),
        "- final article: `%s`" % FINAL,
        "- DOCX: `%s`" % (EXPORT / "manuscript.docx"),
        "- PDF: `%s`" % (EXPORT / "manuscript.pdf"),
        "",
        "## Selected innovation directions",
        "",
    ]
    for item in summary["innovation"]["selected"]:
        lines.append("- %s %s" % (item["idea_id"], item["title"]))
        lines.append("  - falsification: %s" % item["falsification"])
        lines.append("  - evidence: %s" % ", ".join(item["evidence_refs"] or []))
    lines += [
        "",
        "## Comparison",
        "",
        "- baseline: %s" % summary["comparison"]["baseline"],
        "- iterative: %s" % summary["comparison"]["iterative"],
        "- score: %s -> %s (delta %s)"
        % (summary["comparison"]["baseline_score"], summary["comparison"]["final_score"], summary["comparison"]["score_delta"]),
        "- note: %s" % summary["comparison"]["note"],
        "",
        "## Boundary",
        "",
        summary["boundary"],
        "",
    ]
    (PROJECT / "run-summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary": str(PROJECT / "run-summary.md"), "pdf": str(EXPORT / "manuscript.pdf")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
