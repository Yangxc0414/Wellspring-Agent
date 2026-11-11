"""对外部能力的端口；模块只依赖端口，不直接依赖网络/数据库。"""

from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from .contracts import SourceHit, Span

if TYPE_CHECKING:  # avoid runtime circular import; annotations only
    from .rsi import Candidate, EvalEvidence


class RetrieverPort(Protocol):
    fixture_mode: bool

    def search(self, query: str, limit: int) -> List[SourceHit]:
        ...

    def full_text(self, source_id: str) -> Optional[Dict[str, Any]]:
        ...


class ParserPort(Protocol):
    def spans(self, source: SourceHit, document: Dict[str, Any]) -> List[Span]:
        ...


class ModelPort(Protocol):
    """Frozen model boundary used by a proposer; the model is never trained here."""

    model_id: str

    def complete(self, messages: List[Dict[str, str]], json_mode: bool = True) -> str:
        ...


class ProposerPort(Protocol):
    """自进化候选供给接缝。

    平台只定义契约与准入/台账；候选"如何产生"由实现方决定（内部简单自改进、
    外部 Agent、或同学后续的细粒度自进化引擎）。实现不得绕过 GovernancePolicy。
    """

    proposer_id: str

    def propose(self, observation: str) -> List["Candidate"]:
        ...


class EvaluatorPort(Protocol):
    """评测供给接缝：把候选在某个 split 上的表现变成可哈希复核的 EvalEvidence。

    实现方负责真实执行/打分；平台只校验证据形状与哈希，不伪造指标。
    """

    evaluator_id: str

    def evaluate(self, candidate: "Candidate", split: str) -> "EvalEvidence":
        ...
