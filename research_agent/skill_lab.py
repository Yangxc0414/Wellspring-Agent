"""Skill usage evidence and a governed improvement proposal path.

Skills themselves remain instruction catalogs, not executors. This module adds
the missing evidence loop:

    usage receipt -> deterministic evaluation -> pending RSI candidate -> human gate

It deliberately does not rewrite a skill, activate a version, or claim a
capability gain. Imported/custom skills are not executable and therefore cannot
receive a deterministic behavioral evaluation.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .actions import DEFAULT_SKILL_VERSIONS, SKILL_VERSIONS, ActionError, run_skill
from .evolution_policy import EvolutionPolicyError, EvolutionPolicyStore
from .paths import (
    DEFAULT_EVOLUTION_POLICY_PATH,
    DEFAULT_RSI_LEDGER_PATH,
    DEFAULT_SKILL_EVAL_ROOT,
    DEFAULT_SKILL_REGISTRY_PATH,
    DEFAULT_SKILL_USAGE_PATH,
    DEFAULT_SKILL_VERSIONS_PATH,
)
from .rsi import Candidate, RSIController, RSIPolicyError, StepLedger
from .skill_registry import SkillRegistryStore
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic


class SkillLabError(ValueError):
    pass


SKILL_USAGE_SCHEMA = "skill-usage-0.1"
SKILL_EVAL_SCHEMA = "skill-eval-0.1"
SKILL_VERSIONS_SCHEMA = "skill-versions-0.1"
USAGE_STATUSES = ("pass", "warn", "fail", "blocked", "needs_input")
MAX_USAGE_ENTRIES = 500


@dataclass
class SkillUsage:
    usage_id: str
    skill_id: str
    version: str
    task_id: str
    status: str
    checks: List[Dict[str, Any]]
    artifact_ref: str
    note: str
    recorded_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillUsageStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def boundary(self) -> str:
        return (
            "skill usage is invocation evidence, not a capability claim; it never enters "
            "Claim/EA/gate/closure and cannot activate a skill"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            payload = read_json(self.path)
        except JsonStoreError as exc:
            raise SkillLabError(str(exc))
        if payload is None:
            return []
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            raise SkillLabError("skill usage store must contain an entries list")
        return [item for item in payload["entries"] if isinstance(item, dict)]

    def _save(self, entries: List[Dict[str, Any]]) -> None:
        write_json_atomic(
            self.path,
            {
                "schema_version": SKILL_USAGE_SCHEMA,
                "updated_at": now_iso(),
                "count": len(entries),
                "entries": entries[:MAX_USAGE_ENTRIES],
                "boundary": self.boundary,
            },
        )

    def record(
        self,
        skill_id: str,
        version: str,
        task_id: str,
        status: str,
        checks: Optional[List[Dict[str, Any]]] = None,
        artifact_ref: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        skill_id = str(skill_id or "").strip()
        if not skill_id:
            raise SkillLabError("skill_id is required")
        if status not in USAGE_STATUSES:
            raise SkillLabError("status must be one of: " + ", ".join(USAGE_STATUSES))
        entry = SkillUsage(
            usage_id="USE-" + uuid.uuid4().hex[:10],
            skill_id=skill_id,
            version=str(version or "unknown"),
            task_id=str(task_id or ""),
            status=status,
            checks=list(checks or []),
            artifact_ref=str(artifact_ref or ""),
            note=str(note or "")[:500],
            recorded_at=now_iso(),
        ).to_dict()
        entries = self._load()
        entries.insert(0, entry)
        self._save(entries)
        return entry

    def list(self, skill_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        entries = self._load()
        if skill_id:
            entries = [item for item in entries if item.get("skill_id") == skill_id]
        return entries[: max(1, min(int(limit), MAX_USAGE_ENTRIES))]

    def summary(self) -> Dict[str, Any]:
        entries = self._load()
        skills: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            skill_id = str(entry.get("skill_id") or "")
            item = skills.setdefault(
                skill_id,
                {"total": 0, "pass": 0, "warn": 0, "fail": 0, "blocked": 0, "needs_input": 0, "last_at": ""},
            )
            item["total"] += 1
            status = str(entry.get("status") or "")
            if status in item:
                item[status] += 1
            item["last_at"] = max(item["last_at"], str(entry.get("recorded_at") or ""))
        return {
            "schema_version": SKILL_USAGE_SCHEMA,
            "updated_at": now_iso(),
            "count": len(entries),
            "skills": skills,
            "entries": entries[:50],
            "boundary": self.boundary,
        }


@dataclass
class SkillEvalCase:
    case_id: str
    skill_id: str
    split: str
    payload: Dict[str, Any]
    expect: Dict[str, Any]


@dataclass
class SkillEvalReport:
    report_id: str
    skill_id: str
    split: str
    status: str
    passed: int
    failed: int
    pass_rate: float
    cases: List[Dict[str, Any]]
    created_at: str
    boundary: str
    skill_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillVersionStore:
    """Append-only activation records for built-in skill versions.

    Only pre-registered executable built-in versions can be activated. Imported
    or custom skills are rejected because they have no deterministic evaluator.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_SKILL_VERSIONS_PATH)
        self.active: Dict[str, str] = dict(DEFAULT_SKILL_VERSIONS)
        self.history: List[Dict[str, Any]] = []
        self.warning = ""
        self._load()

    @property
    def boundary(self) -> str:
        return (
            "version activation only switches among pre-registered built-in handlers after "
            "public+hidden eval and a human reason; it never rewrites code, executes imported "
            "skills, or creates a capability claim"
        )

    def _load(self) -> None:
        try:
            payload = read_json(self.path)
        except JsonStoreError as exc:
            raise SkillLabError(str(exc))
        if payload is None:
            return
        if not isinstance(payload, dict):
            raise SkillLabError("skill versions store must be an object")
        if payload.get("schema_version") != SKILL_VERSIONS_SCHEMA:
            raise SkillLabError("unsupported skill versions schema")
        active = payload.get("active") or {}
        if not isinstance(active, dict):
            raise SkillLabError("skill versions active must be an object")
        for skill_id, version in active.items():
            if skill_id not in SKILL_VERSIONS or version not in SKILL_VERSIONS[skill_id]:
                raise SkillLabError("unknown active skill version: %s@%s" % (skill_id, version))
            self.active[str(skill_id)] = str(version)
        history = payload.get("history") or []
        if not isinstance(history, list):
            raise SkillLabError("skill versions history must be a list")
        self.history = [item for item in history if isinstance(item, dict)]

    def _save(self) -> None:
        write_json_atomic(self.path, {
            "schema_version": SKILL_VERSIONS_SCHEMA,
            "active": dict(sorted(self.active.items())),
            "history": self.history[-200:],
            "boundary": self.boundary,
            "updated_at": now_iso(),
        })

    def snapshot(self) -> Dict[str, Any]:
        return {
            "schema_version": SKILL_VERSIONS_SCHEMA,
            "active": dict(sorted(self.active.items())),
            "available": {
                skill_id: sorted(versions)
                for skill_id, versions in sorted(SKILL_VERSIONS.items())
            },
            "history": self.history[-50:],
            "boundary": self.boundary,
        }

    def active_version(self, skill_id: str) -> str:
        if skill_id not in SKILL_VERSIONS:
            raise SkillLabError("skill is not executable: " + skill_id)
        return self.active.get(skill_id, DEFAULT_SKILL_VERSIONS[skill_id])

    def activate(self, skill_id: str, version: str, human_reason: str) -> Dict[str, Any]:
        if skill_id not in SKILL_VERSIONS:
            raise SkillLabError("only pre-registered built-in skills can be activated: " + skill_id)
        if version not in SKILL_VERSIONS[skill_id]:
            raise SkillLabError("unknown %s version: %s" % (skill_id, version))
        reason = (human_reason or "").strip()
        if not reason:
            raise SkillLabError("human_reason is required for skill activation")
        previous = self.active.get(skill_id, "")
        if previous == version:
            raise SkillLabError("version is already active: %s@%s" % (skill_id, version))
        record = {
            "action": "activate",
            "skill_id": skill_id,
            "from_version": previous,
            "to_version": version,
            "human_reason": reason[:500],
            "at": now_iso(),
        }
        self.active[skill_id] = version
        self.history.append(record)
        self._save()
        return {"active": dict(sorted(self.active.items())), "record": record}

    def rollback(self, skill_id: str, human_reason: str) -> Dict[str, Any]:
        if skill_id not in SKILL_VERSIONS:
            raise SkillLabError("only pre-registered built-in skills can roll back: " + skill_id)
        reason = (human_reason or "").strip()
        if not reason:
            raise SkillLabError("human_reason is required for rollback")
        current = self.active.get(skill_id, "")
        previous = ""
        for item in reversed(self.history):
            if item.get("skill_id") == skill_id and item.get("from_version"):
                if item.get("to_version") == current:
                    previous = str(item.get("from_version") or "")
                    break
        if not previous:
            available = [v for v in sorted(SKILL_VERSIONS[skill_id]) if v != current]
            previous = available[-1] if available else ""
        if not previous or previous == current:
            raise SkillLabError("no previous version available for " + skill_id)
        record = {
            "action": "rollback",
            "skill_id": skill_id,
            "from_version": current,
            "to_version": previous,
            "human_reason": reason[:500],
            "at": now_iso(),
        }
        self.active[skill_id] = previous
        self.history.append(record)
        self._save()
        return {"active": dict(sorted(self.active.items())), "record": record}


SPAN_A = {
    "span_id": "EVAL-SPAN-1",
    "source_id": "EVAL-SRC-1",
    "section": "Results",
    "text": "湿热条件下钝化层的稳定性结果需要独立重复测量。",
    "start": 0,
    "end": 26,
    "fixture": True,
}
SPAN_B = {
    "span_id": "EVAL-SPAN-2",
    "source_id": "EVAL-SRC-2",
    "section": "Method",
    "text": "实验方法要求记录温度、湿度、样本量与停止条件。",
    "start": 0,
    "end": 24,
    "fixture": True,
}
COMPLETE_PROTOCOL = {
    "hypothesis": "钝化层延长湿热稳定性",
    "baseline": "未钝化对照",
    "metric": "T80",
    "seeds": 3,
    "controls": ["未钝化", "单分子钝化"],
}
EVIDENCE_PASS = [
    {"kind": "claim", "status": "signed", "refs": ["SPAN-1", "EA-1"], "text": "claim"},
    {"kind": "gap", "status": "open", "refs": ["SPAN-1"], "text": "gap"},
]
EVIDENCE_BLOCK = [
    {"kind": "claim", "status": "unsigned", "refs": [], "text": "claim"},
    {"kind": "gap", "status": "open", "refs": [], "text": "gap"},
]

EVAL_CASES: List[SkillEvalCase] = [
    SkillEvalCase(
        "lit-public", "literature-brief", "public",
        {"question": "钙钛矿 界面 钝化 湿热稳定性", "source": "fixture", "max_sources": 6},
        {"status": "ok", "min_spans": 1},
    ),
    SkillEvalCase(
        "lit-hidden", "literature-brief", "hidden",
        {"question": "perovskite passivation humidity stability", "source": "fixture", "max_sources": 6},
        {"status": "ok", "min_spans": 1},
    ),
    SkillEvalCase(
        "idea-public", "hypothesis-triage", "public",
        {"topic": "钝化稳定性", "spans": [SPAN_A, SPAN_B], "max_candidates": 2},
        {"min_candidates": 1},
    ),
    SkillEvalCase(
        "protocol-public", "protocol-review", "public",
        {"protocol": COMPLETE_PROTOCOL},
        {"status": "pass"},
    ),
    SkillEvalCase(
        "protocol-hidden", "protocol-review", "hidden",
        {"protocol": {"hypothesis": "h", "metric": "T80", "seeds": 1}},
        {"status": "needs_input"},
    ),
    SkillEvalCase(
        "evidence-public", "evidence-boundary", "public",
        {"evidence": EVIDENCE_PASS},
        {"status": "pass"},
    ),
    SkillEvalCase(
        "evidence-hidden", "evidence-boundary", "hidden",
        {"evidence": EVIDENCE_BLOCK},
        {"status": "blocked"},
    ),
]


class SkillLab:
    def __init__(
        self,
        registry_path: Optional[Path] = None,
        usage_path: Optional[Path] = None,
        eval_root: Optional[Path] = None,
        ledger_path: Optional[Path] = None,
        policy_path: Optional[Path] = None,
        versions_path: Optional[Path] = None,
    ):
        self.registry = SkillRegistryStore(Path(registry_path or DEFAULT_SKILL_REGISTRY_PATH))
        self.usage = SkillUsageStore(Path(usage_path or DEFAULT_SKILL_USAGE_PATH))
        self.eval_root = Path(eval_root or DEFAULT_SKILL_EVAL_ROOT)
        self.ledger_path = Path(ledger_path or DEFAULT_RSI_LEDGER_PATH)
        self.policy_path = Path(policy_path or DEFAULT_EVOLUTION_POLICY_PATH)
        self.versions = SkillVersionStore(Path(versions_path or DEFAULT_SKILL_VERSIONS_PATH))

    @property
    def boundary(self) -> str:
        return (
            "skill lab evaluates built-in deterministic skills and records usage; "
            "activation/rollback only switches pre-registered built-in versions after "
            "public+hidden eval and a human reason; imported/custom skills are not executable; "
            "proposals remain pending_human only"
        )

    def _skill(self, skill_id: str) -> Dict[str, Any]:
        if skill_id in SKILL_VERSIONS:
            version = self.versions.active_version(skill_id)
            return {
                "id": skill_id,
                "version": version,
                "source": "builtin",
                "executable": True,
                "available_versions": sorted(SKILL_VERSIONS[skill_id]),
            }
        target = next(
            (item for item in self.registry.list() if str(item.get("id")) == skill_id),
            None,
        )
        if target is None:
            raise SkillLabError("skill not found: " + skill_id)
        return {
            "id": skill_id,
            "version": str(target.get("version") or "unknown"),
            "source": str(target.get("source") or "imported"),
            "executable": False,
        }

    def record_usage(
        self,
        skill_id: str,
        status: str,
        task_id: str = "",
        checks: Optional[List[Dict[str, Any]]] = None,
        artifact_ref: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        skill = self._skill(skill_id)
        return self.usage.record(
            skill_id=skill_id,
            version=skill["version"],
            task_id=task_id,
            status=status,
            checks=checks,
            artifact_ref=artifact_ref,
            note=note,
        )

    def evaluate(
        self, skill_id: str, split: str = "all", version: Optional[str] = None
    ) -> SkillEvalReport:
        skill = self._skill(skill_id)
        if split not in ("public", "hidden", "all"):
            raise SkillLabError("split must be public, hidden or all")
        resolved_version = str(version or skill["version"])
        if skill["executable"] and resolved_version not in SKILL_VERSIONS.get(skill_id, {}):
            raise SkillLabError("unknown %s version: %s" % (skill_id, resolved_version))
        if not skill["executable"]:
            report = SkillEvalReport(
                report_id="SEVAL-" + uuid.uuid4().hex[:10],
                skill_id=skill_id,
                split=split,
                status="not_executable",
                passed=0,
                failed=0,
                pass_rate=0.0,
                cases=[],
                created_at=now_iso(),
                boundary=self.boundary,
                skill_version=resolved_version,
            )
            return self._save_eval(report)
        cases = [
            case for case in EVAL_CASES
            if case.skill_id == skill_id and (split == "all" or case.split == split)
        ]
        results = []
        for case in cases:
            try:
                output = run_skill(skill_id, case.payload, version=resolved_version)
                ok, detail = self._expect(output, case.expect)
            except ActionError as exc:
                output = {"error": str(exc)}
                ok, detail = False, str(exc)
            results.append({
                "case_id": case.case_id,
                "split": case.split,
                "status": "pass" if ok else "fail",
                "detail": detail,
                "output_sha256": hashlib.sha256(
                    json.dumps(output, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
            })
        passed = sum(1 for item in results if item["status"] == "pass")
        failed = len(results) - passed
        report = SkillEvalReport(
            report_id="SEVAL-" + uuid.uuid4().hex[:10],
            skill_id=skill_id,
            split=split,
            status="pass" if results and not failed else "fail" if results else "no_cases",
            passed=passed,
            failed=failed,
            pass_rate=round(passed / len(results), 3) if results else 0.0,
            cases=results,
            created_at=now_iso(),
            boundary=self.boundary,
            skill_version=resolved_version,
        )
        return self._save_eval(report)

    @staticmethod
    def _expect(output: Dict[str, Any], expect: Dict[str, Any]) -> tuple:
        if "status" in expect and output.get("status") != expect["status"]:
            return False, "status=%s expected=%s" % (output.get("status"), expect["status"])
        coverage = output.get("coverage") or {}
        if "min_spans" in expect and int(coverage.get("spans", 0)) < int(expect["min_spans"]):
            return False, "spans=%s expected>=%s" % (coverage.get("spans"), expect["min_spans"])
        if "min_candidates" in expect and len(output.get("candidates") or []) < int(expect["min_candidates"]):
            return False, "candidates=%s expected>=%s" % (
                len(output.get("candidates") or []), expect["min_candidates"]
            )
        return True, "ok"

    def _save_eval(self, report: SkillEvalReport) -> SkillEvalReport:
        self.eval_root.mkdir(parents=True, exist_ok=True)
        path = self.eval_root / (
            "%s-%s-%s-%s.json"
            % (report.skill_id, report.skill_version or "unknown", report.split, report.report_id[-6:])
        )
        payload = report.to_dict()
        payload["schema_version"] = SKILL_EVAL_SCHEMA
        write_json_atomic(path, payload)
        report.cases = list(report.cases)
        return report

    def activate(
        self,
        skill_id: str,
        version: str,
        eval_report_path: Path,
        human_reason: str,
    ) -> Dict[str, Any]:
        skill = self._skill(skill_id)
        if not skill["executable"]:
            raise SkillLabError("only executable built-in skills can be activated: " + skill_id)
        if version not in SKILL_VERSIONS.get(skill_id, {}):
            raise SkillLabError("unknown %s version: %s" % (skill_id, version))
        try:
            report = read_json(Path(eval_report_path))
        except JsonStoreError as exc:
            raise SkillLabError(str(exc))
        if not isinstance(report, dict):
            raise SkillLabError("eval report must be a JSON object")
        if report.get("schema_version") != SKILL_EVAL_SCHEMA:
            raise SkillLabError("unsupported eval report schema")
        if report.get("skill_id") != skill_id:
            raise SkillLabError("eval report skill_id does not match")
        if str(report.get("skill_version") or "") != version:
            raise SkillLabError("eval report skill_version does not match")
        if report.get("status") != "pass" or int(report.get("failed") or 0) != 0:
            raise SkillLabError("eval report must pass with zero failures")
        splits = {
            str(item.get("split") or "")
            for item in (report.get("cases") or [])
            if isinstance(item, dict)
        }
        if not {"public", "hidden"}.issubset(splits):
            raise SkillLabError("eval report must include both public and hidden cases")
        result = self.versions.activate(skill_id, version, human_reason)
        return {
            "activation": result,
            "eval_report": str(Path(eval_report_path)),
            "boundary": "activation only switches a pre-registered built-in handler; no code rewrite",
        }

    def rollback(self, skill_id: str, human_reason: str) -> Dict[str, Any]:
        return {
            "rollback": self.versions.rollback(skill_id, human_reason),
            "boundary": "rollback only switches to a previously registered built-in version",
        }

    def proposal_observation(self, skill_id: str) -> str:
        summary = self.usage.summary()
        item = (summary.get("skills") or {}).get(skill_id) or {}
        return (
            "skill=%s usage_total=%s pass=%s warn=%s fail=%s blocked=%s needs_input=%s"
            % (
                skill_id,
                item.get("total", 0),
                item.get("pass", 0),
                item.get("warn", 0),
                item.get("fail", 0),
                item.get("blocked", 0),
                item.get("needs_input", 0),
            )
        )

    def propose(
        self,
        skill_id: str,
        patch: str,
        rationale: str,
        predicted_effect: str,
        dry_run_ref: str = "",
        observation: str = "",
    ) -> Dict[str, Any]:
        skill = self._skill(skill_id)
        if not patch.strip() or not rationale.strip() or not predicted_effect.strip():
            raise SkillLabError("patch, rationale and predicted_effect are required")
        usage = self.proposal_observation(skill_id)
        if int((self.usage.summary().get("skills", {}).get(skill_id) or {}).get("total", 0)) == 0:
            raise SkillLabError("record at least one usage receipt before proposing a skill change")
        try:
            self.policy = EvolutionPolicyStore(self.policy_path)
            self.policy.require_candidate("skill", "skill:" + skill_id)
        except EvolutionPolicyError as exc:
            raise SkillLabError(str(exc))
        target = "skill:%s@%s" % (skill_id, skill["version"])
        try:
            record = RSIController(StepLedger.load(self.ledger_path)).propose(
                Candidate(
                    kind="skill",
                    target=target,
                    patch=patch.strip(),
                    rationale=(rationale.strip() + "\n" + usage + ("\n" + observation if observation else "")),
                    predicted_effect=predicted_effect.strip(),
                    scope="skill/" + skill_id,
                ),
                observation=usage,
                dry_run_ref=dry_run_ref,
            )
        except (RSIPolicyError, OSError, ValueError) as exc:
            raise SkillLabError(str(exc))
        return {
            "candidate": asdict(record),
            "usage": usage,
            "boundary": "pending_human only; no automatic skill rewrite, activation or capability claim",
        }
