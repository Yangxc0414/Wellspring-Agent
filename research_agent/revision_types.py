"""Data objects for existing-manuscript revision (S8–S12)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    rows: List[List[str]] = field(default_factory=list)
    image: str = ""
    caption: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {"kind": self.kind, "text": self.text}
        if self.level:
            value["level"] = self.level
        if self.rows:
            value["rows"] = [list(row) for row in self.rows]
        if self.image:
            value["image"] = self.image
        if self.caption:
            value["caption"] = self.caption
        if self.meta:
            value["meta"] = dict(self.meta)
        return value


@dataclass
class Section:
    heading: str
    level: int
    blocks: List[Block] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heading": self.heading,
            "level": self.level,
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass
class DraftDocument:
    title: str
    sections: List[Section]
    source: str = ""
    source_sha256: str = ""
    language: str = "zh"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "source_sha256": self.source_sha256,
            "language": self.language,
            "sections": [section.to_dict() for section in self.sections],
            "warnings": list(self.warnings),
        }


@dataclass
class DataTable:
    name: str
    path: str
    columns: List[str]
    rows: List[Dict[str, str]]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "columns": list(self.columns),
            "row_count": len(self.rows),
            "warnings": list(self.warnings),
        }


@dataclass
class MetricResult:
    name: str
    value: Optional[float]
    formatted: str
    op: str
    table: str
    column: str
    count: int
    digits: int
    where: Dict[str, Any] = field(default_factory=dict)
    replacements: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "formatted": self.formatted,
            "op": self.op,
            "table": self.table,
            "column": self.column,
            "count": self.count,
            "digits": self.digits,
            "where": dict(self.where),
            "replacements": self.replacements,
            "error": self.error,
        }
