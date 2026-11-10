"""对外部能力的端口；模块只依赖端口，不直接依赖网络/数据库。"""

from typing import Any, Dict, List, Optional, Protocol

from .contracts import SourceHit, Span


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
