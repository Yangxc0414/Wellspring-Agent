"""Grant-track scaffold for NSFC/NSSFC-style proposals."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..contracts import GrantPlan
from ..specs import ModuleSpec


class GrantError(RuntimeError):
    pass


@dataclass
class GrantRequest:
    topic: str
    scheme: str = "nsfc"
    evidence_refs: List[str] = field(default_factory=list)


SCHEMES = {
    "nsfc": {
        "name": "国家自然科学基金（NSFC）",
        "modules": ["立项依据", "研究内容", "研究基础", "创新点", "预算说明"],
        "compliance": ["三模块/页限以当年官方模板为准", "AI 辅助声明", "科学观点由申请人提供"],
    },
    "nssfc": {
        "name": "国家社会科学基金（NSSFC）",
        "modules": ["选题说明", "选题依据", "研究内容", "创新之处", "研究基础", "经费概算", "活页匿名"],
        "compliance": ["选题说明字数以当年模板为准", "活页匿名", "科学观点由申请人提供"],
    },
    "generic": {
        "name": "通用研究计划",
        "modules": ["问题与目标", "研究内容", "方法", "计划", "基础", "预算"],
        "compliance": ["按资助机构模板核对页限/匿名/声明"],
    },
}


def grant_template(scheme: str = "nsfc") -> Dict[str, Any]:
    """Blank, filled-by-the-applicant section skeleton for one scheme."""
    config = SCHEMES.get(scheme)
    if config is None:
        raise GrantError("unknown grant scheme: " + scheme)
    return {
        "schema_version": "grant-draft-0.1",
        "scheme": scheme,
        "title": "",
        "sections": {module: "" for module in config["modules"]},
        "evidence_refs": [],
        "anonymous": scheme == "nssfc",
        "identity_removed": scheme == "nssfc",
        "ai_statement": False,
        "compliance": list(config["compliance"]),
        "boundary": (
            "blank scaffold only: the applicant supplies scientific ideas, text and budget; "
            "official template and current call win; nothing is submitted or signed"
        ),
    }


class GrantAgent:
    module_id = "grant"

    def __init__(self, spec: ModuleSpec):
        if spec.id != self.module_id:
            raise GrantError("spec id must be 'grant'")
        self.spec = spec

    def run(self, request: GrantRequest) -> GrantPlan:
        if self.spec.status in ("revoked", "deprecated"):
            raise GrantError("module spec status is %s; refusing to run" % self.spec.status)
        if not request.topic.strip():
            raise GrantError("topic is required")
        scheme = SCHEMES.get(request.scheme)
        if scheme is None:
            raise GrantError("unknown grant scheme: " + request.scheme)
        warnings = [
            "scheme=%s; scaffold only: no scientific claims, no budget numbers, no submission" % scheme["name"],
            "AI assists retrieval/structure/polish; scientific ideas and responsibility stay with the applicant",
            "official template / page limit must be checked against the current call",
        ]
        if not request.evidence_refs:
            warnings.append("no evidence_refs supplied")
        return GrantPlan(
            title="申报草稿：%s" % request.topic.strip(),
            scheme=request.scheme,
            modules=list(scheme["modules"]),
            compliance=list(scheme["compliance"]),
            evidence_refs=list(request.evidence_refs),
            status="draft_needs_human",
            warnings=warnings,
        )
