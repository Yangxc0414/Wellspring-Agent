"""Parse existing manuscripts/data and export revised manuscript packages."""

import copy
import csv
import hashlib
import html
import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .revision_templates import get_venue_profile
from .revision_types import Block, DataTable, DraftDocument, MetricResult, Section

DRAFT_SUFFIXES = (".md", ".markdown", ".txt", ".docx", ".tex")
DATA_SUFFIXES = (".csv", ".tsv", ".json", ".xlsx")
REFERENCE_HEADINGS = ("参考文献", "references", "bibliography")
SKIP_SECTION_MARKERS = REFERENCE_HEADINGS + ("致谢", "acknowledg", "附录", "appendix")
FIGURE_CAPTION_RE = re.compile(r"^\s*(图|表|figure|table)\s*[0-9一二三四五六七八九十]+", re.I)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?[0-9]+(?:\.[0-9]+)?%?(?![A-Za-z0-9])")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


class RevisionIOError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_caption(text: str) -> bool:
    return bool(FIGURE_CAPTION_RE.match(text or ""))


def _is_reference_heading(heading: str) -> bool:
    lowered = str(heading or "").strip().lower()
    return any(marker in lowered for marker in REFERENCE_HEADINGS)


def _is_skip_heading(heading: str) -> bool:
    lowered = str(heading or "").strip().lower()
    return any(marker in lowered for marker in SKIP_SECTION_MARKERS)


def _new_section(sections: List[Section], heading: str, level: int) -> Section:
    section = Section(heading=heading, level=level)
    sections.append(section)
    return section


def _append_block(
    sections: List[Section],
    block: Block,
    in_references: bool = False,
) -> None:
    if in_references:
        block.kind = "reference"
    if not sections:
        sections.append(Section(heading="", level=0))
    sections[-1].blocks.append(block)


def _parse_table_lines(lines: List[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in lines:
        stripped = line.strip().strip("|")
        if not stripped:
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        rows.append(cells)
    if len(rows) >= 2 and all(re.match(r"^:?-{3,}:?$", cell) for cell in rows[1]):
        rows = [rows[0]] + rows[2:]
    return rows


def _resolve_image_path(value: str, source: str) -> str:
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://", "data:")):
        return text
    path = Path(text)
    if path.is_absolute():
        return str(path)
    return str((Path(source).parent / path).resolve())


def _parse_markdown(raw: str, source: str) -> DraftDocument:
    sections: List[Section] = []
    title = ""
    warnings: List[str] = []
    in_references = False
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    paragraph: List[str] = []

    def flush() -> None:
        nonlocal paragraph
        text = "\n".join(paragraph).strip()
        if text:
            kind = "caption" if _is_caption(text) else "paragraph"
            _append_block(
                sections,
                Block(kind=kind, text=text),
                in_references=in_references,
            )
        paragraph = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            language = stripped[3:].strip()
            code: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            _append_block(
                sections,
                Block(kind="code", text="\n".join(code), meta={"language": language}),
                in_references=in_references,
            )
            i += 1
            continue
        if stripped.startswith("$$"):
            flush()
            math_lines = [stripped]
            if not (stripped.endswith("$$") and len(stripped) > 4):
                i += 1
                while i < len(lines) and not lines[i].strip().endswith("$$"):
                    math_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    math_lines.append(lines[i])
            _append_block(
                sections,
                Block(kind="equation", text="\n".join(math_lines)),
                in_references=in_references,
            )
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1 and not title:
                title = text
            else:
                in_references = _is_reference_heading(text)
                _new_section(sections, text, level)
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines):
            separator = lines[i + 1].strip()
            if re.match(r"^\|?\s*:?-{3,}", separator):
                flush()
                table_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                _append_block(
                    sections,
                    Block(kind="table", rows=_parse_table_lines(table_lines)),
                    in_references=in_references,
                )
                continue
        image_match = IMAGE_RE.search(line)
        if image_match:
            flush()
            _append_block(
                sections,
                Block(
                    kind="figure",
                    image=_resolve_image_path(image_match.group(2).strip(), source),
                    caption=image_match.group(1).strip(),
                ),
                in_references=in_references,
            )
            i += 1
            continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            flush()
            text = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line).strip()
            _append_block(
                sections,
                Block(kind="bullet", text=text),
                in_references=in_references,
            )
            i += 1
            continue
        if not stripped:
            flush()
            i += 1
            continue
        paragraph.append(line.strip())
        i += 1
    flush()
    if not title:
        title = Path(source).stem
    if not sections:
        warnings.append("no headings found; the whole document is treated as one section")
        sections.append(Section(heading="", level=0))
    return DraftDocument(
        title=title,
        sections=sections,
        source=source,
        source_sha256=sha256_text(raw),
        language="zh" if re.search(r"[\u4e00-\u9fff]", raw) else "en",
        warnings=warnings,
    )


def _docx_heading_level(style_name: str) -> int:
    lowered = str(style_name or "").strip().lower()
    match = re.search(r"(\d+)$", lowered)
    if "heading" in lowered or "标题" in lowered:
        return int(match.group(1)) if match else 1
    return 0


def _extract_docx_images(paragraph: Any, doc: Any, assets_dir: Path) -> List[str]:
    paths: List[str] = []
    try:
        rel_ids = paragraph._p.xpath(".//a:blip/@r:embed")
    except Exception:
        rel_ids = []
    for index, rel_id in enumerate(rel_ids, 1):
        try:
            part = doc.part.related_parts[rel_id]
            blob = getattr(part, "blob", b"")
            partname = str(getattr(part, "partname", "image.bin"))
            suffix = Path(partname).suffix or ".bin"
            name = "docx-image-%s-%d%s" % (sha256_text(str(rel_id))[:8], index, suffix)
            target = assets_dir / name
            if not target.is_file():
                target.write_bytes(blob)
            paths.append(str(target))
        except Exception:
            continue
    return paths


def _parse_docx(path: Path, assets_dir: Optional[Path]) -> DraftDocument:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RevisionIOError("python-docx is required to read DOCX: %s" % exc)
    doc = Document(str(path))
    sections: List[Section] = []
    title = ""
    warnings: List[str] = []
    in_references = False
    assets = Path(assets_dir) if assets_dir else path.parent / "revision-assets"
    assets.mkdir(parents=True, exist_ok=True)
    for child in doc.element.body.iterchildren():
        tag = str(child.tag).lower()
        if tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            text = _clean_text(paragraph.text)
            style = str(getattr(paragraph.style, "name", "") or "")
            level = _docx_heading_level(style)
            if "title" in style.lower() and text:
                if not title:
                    title = text
                continue
            if level > 0 and text:
                if level == 1 and not title:
                    title = text
                else:
                    in_references = _is_reference_heading(text)
                    _new_section(sections, text, level)
                continue
            images = _extract_docx_images(paragraph, doc, assets)
            if text:
                kind = "caption" if _is_caption(text) else "paragraph"
                if "list" in style.lower() or paragraph._p.xpath(".//w:numPr"):
                    kind = "bullet"
                _append_block(
                    sections,
                    Block(kind=kind, text=text),
                    in_references=in_references,
                )
            for image in images:
                _append_block(
                    sections,
                    Block(kind="figure", image=image, caption=text if _is_caption(text) else ""),
                    in_references=in_references,
                )
            continue
        if tag.endswith("}tbl"):
            table = Table(child, doc)
            rows: List[List[str]] = []
            for row in table.rows:
                rows.append([_clean_text(cell.text) for cell in row.cells])
            if rows:
                _append_block(
                    sections,
                    Block(kind="table", rows=rows),
                    in_references=in_references,
                )
    if not title:
        title = path.stem
    if not sections:
        sections.append(Section(heading="", level=0))
    return DraftDocument(
        title=title,
        sections=sections,
        source=str(path),
        source_sha256=sha256_file(path),
        language="zh" if re.search(r"[\u4e00-\u9fff]", "\n".join(
            block.text for section in sections for block in section.blocks
        )) else "en",
        warnings=warnings,
    )


def _parse_tex(raw: str, source: str) -> DraftDocument:
    text = re.sub(r"(?<!\\)%.*", "", raw)
    document_match = re.search(r"\\begin\{document\}([\s\S]*?)\\end\{document\}", text)
    body = document_match.group(1) if document_match else text
    title_match = re.search(r"\\title\{([^{}]*)\}", text)
    title = _clean_text(title_match.group(1)) if title_match else ""
    sections: List[Section] = []
    warnings = ["TeX import is best-effort; complex macros/tables may need manual review"]
    current = Section(heading="", level=0)
    sections.append(current)
    chunks = re.split(r"\n\s*\n", body)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        heading = re.match(
            r"\\(section|subsection|subsubsection)\*?\{([^{}]*)\}", chunk
        )
        if heading:
            level = {"section": 1, "subsection": 2, "subsubsection": 3}[heading.group(1)]
            _new_section(sections, _clean_text(heading.group(2)), level)
            chunk = chunk[heading.end():].strip()
        if not chunk:
            continue
        image = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", chunk)
        if image and len(chunk) < 300:
            _append_block(
                sections,
                Block(kind="figure", image=_resolve_image_path(image.group(1).strip(), source)),
            )
            continue
        cleaned = re.sub(r"\\(cite|ref|label|textbf|textit|emph)\{([^{}]*)\}", r"\2", chunk)
        cleaned = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", cleaned)
        cleaned = cleaned.replace("{", "").replace("}", "").replace("~", " ")
        _append_block(
            sections,
            Block(kind="equation" if "\\begin{" in chunk else "paragraph", text=cleaned.strip()),
        )
    return DraftDocument(
        title=title or Path(source).stem,
        sections=sections,
        source=source,
        source_sha256=sha256_text(raw),
        language="zh" if re.search(r"[\u4e00-\u9fff]", raw) else "en",
        warnings=warnings,
    )


def read_draft(path: Path, assets_dir: Optional[Path] = None) -> DraftDocument:
    source = Path(path)
    if not source.is_file():
        raise RevisionIOError("manuscript draft does not exist: %s" % source)
    suffix = source.suffix.lower()
    if suffix == ".docx":
        return _parse_docx(source, assets_dir)
    try:
        raw = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = source.read_text(encoding="utf-8", errors="replace")
    if suffix == ".tex":
        return _parse_tex(raw, str(source))
    return _parse_markdown(raw, str(source))


def iter_text_blocks(document: DraftDocument) -> Iterable[Tuple[Section, Block]]:
    for section in document.sections:
        for block in section.blocks:
            if block.kind in ("paragraph", "bullet", "caption"):
                yield section, block


def extract_numbers(text: str) -> List[str]:
    return [match.group(0) for match in NUMBER_RE.finditer(text or "")]


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _row_value(row: Dict[str, str], column: str) -> str:
    return str(row.get(column, "") or "").strip()


def _filter_rows(rows: List[Dict[str, str]], where: Dict[str, Any]) -> List[Dict[str, str]]:
    if not where:
        return list(rows)
    selected = []
    for row in rows:
        if all(str(row.get(key, "")).strip() == str(value).strip() for key, value in where.items()):
            selected.append(row)
    return selected


def _find_table(tables: List[DataTable], name: str) -> DataTable:
    wanted = str(name or "").strip().lower()
    if not wanted:
        if len(tables) == 1:
            return tables[0]
        raise RevisionIOError("metric/figure needs a table name when multiple tables are loaded")
    for table in tables:
        if table.name.lower() == wanted or Path(table.path).stem.lower() == wanted:
            return table
    raise RevisionIOError("data table not found: " + name)


def load_json_records(path: Path) -> List[Dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RevisionIOError("cannot read JSON table %s: %s" % (path, exc))
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            data = data["rows"]
        elif isinstance(data.get("data"), list):
            data = data["data"]
        elif all(isinstance(value, list) for value in data.values()):
            length = max((len(value) for value in data.values()), default=0)
            data = [
                {key: (values[index] if index < len(values) else "") for key, values in data.items()}
                for index in range(length)
            ]
    if not isinstance(data, list):
        raise RevisionIOError("JSON table must be a list of objects or an object with rows[]")
    rows: List[Dict[str, str]] = []
    for item in data:
        if isinstance(item, dict):
            rows.append({str(key): str(value if value is not None else "") for key, value in item.items()})
        else:
            rows.append({"value": str(item)})
    return rows


def load_data_tables(paths: Sequence[Path]) -> List[DataTable]:
    tables: List[DataTable] = []
    for path in paths:
        source = Path(path)
        if not source.is_file():
            raise RevisionIOError("data file does not exist: %s" % source)
        suffix = source.suffix.lower()
        if suffix not in DATA_SUFFIXES:
            raise RevisionIOError("unsupported data file: %s" % suffix)
        if suffix == ".xlsx":
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise RevisionIOError("openpyxl is required for XLSX: %s" % exc)
            workbook = load_workbook(str(source), read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    rows_iter = sheet.iter_rows(values_only=True)
                    header = next(rows_iter, None)
                    if not header:
                        continue
                    columns = [str(value if value is not None else "col%d" % index) for index, value in enumerate(header)]
                    rows = []
                    for values in rows_iter:
                        if values is None:
                            continue
                        row = {}
                        for index, column in enumerate(columns):
                            value = values[index] if index < len(values) else ""
                            row[column] = "" if value is None else str(value)
                        rows.append(row)
                    tables.append(
                        DataTable(
                            name="%s:%s" % (source.stem, sheet.title),
                            path=str(source),
                            columns=columns,
                            rows=rows,
                        )
                    )
            finally:
                workbook.close()
            continue
        if suffix == ".json":
            rows = load_json_records(source)
        else:
            delimiter = "\t" if suffix == ".tsv" else ","
            with open(str(source), "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                rows = [{str(key): str(value or "") for key, value in row.items()} for row in reader]
        columns = list(rows[0].keys()) if rows else []
        tables.append(
            DataTable(name=source.stem, path=str(source), columns=columns, rows=rows)
        )
    return tables


def profile_tables(tables: List[DataTable]) -> List[Dict[str, Any]]:
    profiles = []
    for table in tables:
        columns = []
        for column in table.columns:
            values = [_row_value(row, column) for row in table.rows]
            nonempty = [value for value in values if value]
            numbers = [_as_number(value) for value in nonempty]
            numeric = [value for value in numbers if value is not None]
            item: Dict[str, Any] = {
                "name": column,
                "nonempty": len(nonempty),
                "missing": len(values) - len(nonempty),
                "numeric_count": len(numeric),
            }
            if numeric:
                item.update(
                    {
                        "min": min(numeric),
                        "max": max(numeric),
                        "mean": sum(numeric) / len(numeric),
                        "std": statistics.stdev(numeric) if len(numeric) > 1 else 0.0,
                    }
                )
            columns.append(item)
        profiles.append(
            {
                "table": table.name,
                "path": table.path,
                "rows": len(table.rows),
                "columns": columns,
                "warnings": list(table.warnings),
            }
        )
    return profiles


def load_metric_specs(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RevisionIOError("cannot read metric spec: %s" % exc)
    metrics = data.get("metrics") if isinstance(data, dict) else data
    if not isinstance(metrics, list):
        raise RevisionIOError("metric spec must contain a metrics list")
    normalized = []
    for index, item in enumerate(metrics):
        if not isinstance(item, dict):
            raise RevisionIOError("metric #%d must be an object" % index)
        if not str(item.get("name") or "").strip():
            raise RevisionIOError("metric #%d needs a name" % index)
        normalized.append(
            {
                "name": str(item["name"]).strip(),
                "table": str(item.get("table") or ""),
                "column": str(item.get("column") or ""),
                "op": str(item.get("op") or "mean").strip().lower(),
                "where": item.get("where") if isinstance(item.get("where"), dict) else {},
                "digits": int(item.get("digits", 4)),
                "replace": item.get("replace", []),
                "section": str(item.get("section") or ""),
                "equals": item.get("equals"),
            }
        )
    return normalized


def compute_metrics(
    tables: List[DataTable], specs: List[Dict[str, Any]]
) -> List[MetricResult]:
    results: List[MetricResult] = []
    for spec in specs:
        table_name = spec.get("table", "")
        try:
            table = _find_table(tables, table_name)
        except RevisionIOError as exc:
            results.append(
                MetricResult(
                    name=spec["name"], value=None, formatted="", op=spec.get("op", ""),
                    table=table_name, column=spec.get("column", ""), count=0,
                    digits=int(spec.get("digits", 4)), where=dict(spec.get("where") or {}),
                    error=str(exc),
                )
            )
            continue
        rows = _filter_rows(table.rows, spec.get("where") or {})
        column = spec.get("column", "")
        op = spec.get("op", "mean")
        values = [_row_value(row, column) for row in rows] if column and column != "*" else []
        numbers = [_as_number(value) for value in values]
        numeric = [value for value in numbers if value is not None]
        value: Optional[float] = None
        error = ""
        try:
            if op == "count":
                value = float(len(rows) if column in ("", "*") else len([v for v in values if v]))
            elif not numeric:
                raise RevisionIOError("no numeric values for %s.%s" % (table.name, column))
            elif op == "mean":
                value = sum(numeric) / len(numeric)
            elif op == "sum":
                value = sum(numeric)
            elif op == "min":
                value = min(numeric)
            elif op == "max":
                value = max(numeric)
            elif op == "median":
                value = statistics.median(numeric)
            elif op == "std":
                value = statistics.stdev(numeric) if len(numeric) > 1 else 0.0
            elif op == "proportion":
                equals = spec.get("equals")
                if equals is None:
                    matched = [v for v in values if v.lower() in ("1", "true", "yes", "y")]
                else:
                    matched = [v for v in values if v == str(equals)]
                value = len(matched) / len(values) if values else None
            else:
                raise RevisionIOError("unsupported metric op: " + op)
        except RevisionIOError as exc:
            error = str(exc)
        digits = int(spec.get("digits", 4))
        if value is None:
            formatted = ""
        elif op == "count":
            formatted = str(int(value))
        else:
            formatted = ("%." + str(digits) + "f") % value
        results.append(
            MetricResult(
                name=spec["name"],
                value=value,
                formatted=formatted,
                op=op,
                table=table.name,
                column=column,
                count=len(rows) if column in ("", "*") else len(numeric),
                digits=digits,
                where=dict(spec.get("where") or {}),
                error=error,
            )
        )
    return results


def _replace_values(text: str, old_values: Sequence[str], new_value: str) -> Tuple[str, int]:
    count = 0
    result = text
    for old in old_values:
        old = str(old)
        if not old:
            continue
        occurrences = result.count(old)
        if occurrences:
            result = result.replace(old, new_value)
            count += occurrences
    return result, count


def apply_metric_replacements(
    document: DraftDocument,
    metrics: Sequence[MetricResult],
    specs: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    spec_by_name = {str(spec.get("name")): spec for spec in specs}
    records: List[Dict[str, Any]] = []
    for section in document.sections:
        for block in section.blocks:
            if block.kind not in ("paragraph", "bullet", "caption"):
                continue
            original = block.text
            text = original
            for metric in metrics:
                placeholder = "{{metric:%s}}" % metric.name
                if placeholder in text and metric.formatted:
                    text = text.replace(placeholder, metric.formatted)
            for metric in metrics:
                spec = spec_by_name.get(metric.name) or {}
                target_section = str(spec.get("section") or "").strip()
                if target_section and target_section not in section.heading:
                    continue
                old = spec.get("replace")
                if not old or not metric.formatted:
                    continue
                old_values = old if isinstance(old, list) else [old]
                text, count = _replace_values(text, [str(item) for item in old_values], metric.formatted)
                if count:
                    metric.replacements += count
                    records.append(
                        {
                            "metric": metric.name,
                            "section": section.heading,
                            "old": old_values,
                            "new": metric.formatted,
                            "occurrences": count,
                        }
                    )
            block.text = text
    return records


def _table_markdown(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_markdown(document: DraftDocument) -> str:
    lines: List[str] = []
    if document.title:
        lines += ["# " + document.title, ""]
    for section in document.sections:
        if section.heading:
            prefix = "#" * min(6, max(1, section.level))
            lines += [prefix + " " + section.heading, ""]
        for block in section.blocks:
            if block.kind == "table":
                lines += [_table_markdown(block.rows), ""]
            elif block.kind == "figure":
                if block.image:
                    lines += ["![%s](%s)" % (block.caption or "figure", block.image), ""]
                elif block.caption:
                    lines += ["*%s*" % block.caption, ""]
            elif block.kind == "code":
                lines += ["```" + str(block.meta.get("language") or ""), block.text, "```", ""]
            elif block.kind == "equation":
                lines += ["$$", block.text.strip("$").strip(), "$$", ""]
            elif block.kind == "reference":
                lines += [block.text, ""]
            else:
                lines += [block.text, ""]
    return "\n".join(lines).rstrip() + "\n"


def _tex_escape(value: str) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def render_latex(document: DraftDocument, profile: Dict[str, Any]) -> str:
    width = float(profile.get("figure_width_cm") or 15.5)
    heading_levels = [section.level for section in document.sections if section.heading]
    base_level = min(heading_levels) if heading_levels else 1
    lines = [
        r"\documentclass[UTF8]{ctexart}",
        r"\usepackage[a4paper,margin=2.2cm]{geometry}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue]{hyperref}",
        r"\title{%s}" % _tex_escape(document.title),
        r"\begin{document}",
        r"\maketitle",
        "",
    ]
    for section in document.sections:
        if section.heading:
            relative_level = section.level - base_level + 1
            command = {
                1: "section",
                2: "subsection",
                3: "subsubsection",
            }.get(relative_level, "paragraph")
            lines += [r"\%s{%s}" % (command, _tex_escape(section.heading)), ""]
        for block in section.blocks:
            if block.kind == "table":
                if not block.rows:
                    continue
                width_cols = max(len(row) for row in block.rows)
                spec = "l" * width_cols
                lines += [r"\begin{longtable}{%s}" % spec, r"\toprule"]
                for index, row in enumerate(block.rows):
                    cells = [_tex_escape(cell) for cell in row]
                    if len(cells) < width_cols:
                        cells += [""] * (width_cols - len(cells))
                    lines.append(" & ".join(cells) + r" \\")
                    if index == 0:
                        lines.append(r"\midrule")
                lines += [r"\bottomrule", r"\end{longtable}", ""]
            elif block.kind == "figure":
                image = block.image.replace("\\", "/")
                if image:
                    lines += [
                        r"\begin{figure}[htbp]",
                        r"\centering",
                        r"\includegraphics[width=%.2fcm]{%s}" % (width, image),
                        r"\caption{%s}" % _tex_escape(block.caption),
                        r"\end{figure}",
                        "",
                    ]
            elif block.kind == "code":
                lines += [r"\begin{verbatim}", block.text, r"\end{verbatim}", ""]
            elif block.kind == "equation":
                lines += [r"\begin{equation}", block.text.strip("$").strip(), r"\end{equation}", ""]
            elif block.kind == "reference":
                lines += [r"\noindent %s\par" % _tex_escape(block.text), ""]
            else:
                lines += [_tex_escape(block.text), ""]
    lines += [r"\end{document}", ""]
    return "\n".join(lines)


def _set_docx_font(run: Any, size: float, bold: bool = False, cn: str = "宋体") -> None:
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), cn)
    run.font.size = Pt(size)
    run.bold = bold


def _render_docx(document: DraftDocument, profile: Dict[str, Any], output: Path) -> None:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Cm, Pt
    except ImportError as exc:
        raise RevisionIOError("python-docx is required for DOCX export: %s" % exc)
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(float(profile.get("page_width_cm") or 21.0))
    section.page_height = Cm(float(profile.get("page_height_cm") or 29.7))
    section.top_margin = Cm(float(profile.get("margin_top_cm") or 2.4))
    section.bottom_margin = Cm(float(profile.get("margin_bottom_cm") or 2.4))
    section.left_margin = Cm(float(profile.get("margin_left_cm") or 2.4))
    section.right_margin = Cm(float(profile.get("margin_right_cm") or 2.4))
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(float(profile.get("body_pt") or 10.5))
    from docx.oxml.ns import qn
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    body_pt = float(profile.get("body_pt") or 10.5)
    heading_pt = float(profile.get("heading_pt") or 12.0)
    title_pt = float(profile.get("title_pt") or 18.0)
    reference_pt = float(profile.get("reference_pt") or 9.0)
    figure_width = float(profile.get("figure_width_cm") or 15.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(document.title)
    _set_docx_font(run, title_pt, True, "黑体")

    for sec in document.sections:
        if sec.heading:
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(sec.heading)
            _set_docx_font(run, heading_pt, True, "黑体")
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(3)
        for block in sec.blocks:
            if block.kind == "table":
                if not block.rows:
                    continue
                cols = max(len(row) for row in block.rows)
                table = doc.add_table(rows=len(block.rows), cols=cols)
                table.style = "Table Grid"
                for r_index, row in enumerate(block.rows):
                    for c_index in range(cols):
                        cell = table.cell(r_index, c_index)
                        cell.text = row[c_index] if c_index < len(row) else ""
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                _set_docx_font(run, 8.0)
                doc.add_paragraph("")
            elif block.kind == "figure":
                if block.image:
                    image_path = Path(block.image)
                    if image_path.is_file() and image_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                        paragraph = doc.add_paragraph()
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        paragraph.add_run().add_picture(str(image_path), width=Cm(figure_width))
                if block.caption:
                    caption = doc.add_paragraph()
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    _set_docx_font(caption.add_run(block.caption), 9.0)
            elif block.kind == "code":
                paragraph = doc.add_paragraph()
                _set_docx_font(paragraph.add_run(block.text), body_pt - 0.5, False, "Consolas")
            elif block.kind == "equation":
                paragraph = doc.add_paragraph()
                _set_docx_font(paragraph.add_run(block.text), body_pt)
            elif block.kind == "reference":
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.first_line_indent = Cm(-0.6)
                paragraph.paragraph_format.left_indent = Cm(0.6)
                _set_docx_font(paragraph.add_run(block.text), reference_pt)
            else:
                paragraph = doc.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                paragraph.paragraph_format.first_line_indent = Cm(0.66)
                _set_docx_font(paragraph.add_run(block.text), body_pt)
    doc.save(str(output))


def _render_html(document: DraftDocument) -> str:
    body = []
    if document.title:
        body.append("<h1>%s</h1>" % html.escape(document.title))
    for section in document.sections:
        if section.heading:
            body.append("<h2>%s</h2>" % html.escape(section.heading))
        for block in section.blocks:
            if block.kind == "table":
                body.append("<table>")
                for row in block.rows:
                    body.append("<tr>" + "".join("<td>%s</td>" % html.escape(cell) for cell in row) + "</tr>")
                body.append("</table>")
            elif block.kind == "figure":
                if block.image:
                    body.append('<figure><img src="%s" alt="%s"><figcaption>%s</figcaption></figure>' % (
                        html.escape(block.image), html.escape(block.caption), html.escape(block.caption)
                    ))
            elif block.kind == "code":
                body.append("<pre>%s</pre>" % html.escape(block.text))
            else:
                body.append("<p>%s</p>" % html.escape(block.text))
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<style>body{font-family:'Microsoft YaHei',serif;max-width:900px;margin:40px auto;"
        "line-height:1.7;color:#222}h1{text-align:center}h2{margin-top:1.4em}"
        "table{border-collapse:collapse;width:100%}td{border:1px solid #aaa;padding:4px}"
        "figure{text-align:center}img{max-width:100%}</style></head><body>"
        + "\n".join(body)
        + "</body></html>"
    )


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Tuple[Optional[Path], str]:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None, "LibreOffice/soffice not found; DOCX created, PDF skipped"
    profile = Path(tempfile.mkdtemp(prefix="revision-lo-"))
    command = [
        soffice, "--headless", "--norestore",
        "-env:UserInstallation=file:///" + profile.as_posix(),
        "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "PDF conversion failed: %s" % exc
    target = output_dir / (docx_path.stem + ".pdf")
    if completed.returncode != 0 or not target.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-300:]
        return None, "PDF conversion failed: " + (detail or "unknown error")
    return target, ""


def _materialize_images(document: DraftDocument, output: Path) -> DraftDocument:
    """Copy local images into export/images and use portable relative paths."""
    prepared = copy.deepcopy(document)
    images_dir = output / "images"
    used: Dict[str, str] = {}
    for section in prepared.sections:
        for block in section.blocks:
            if block.kind != "figure" or not block.image:
                continue
            source = Path(block.image)
            if not source.is_file():
                continue
            name = source.name
            if name in used and used[name] != str(source.resolve()):
                name = "%s-%s%s" % (source.stem, sha256_text(str(source.resolve()))[:6], source.suffix)
            used[name] = str(source.resolve())
            images_dir.mkdir(parents=True, exist_ok=True)
            target = images_dir / name
            if not target.is_file():
                shutil.copyfile(str(source), str(target))
            block.image = "images/" + name
    return prepared


def export_document(
    document: DraftDocument,
    output_dir: Path,
    venue: str = "zh_core_journal",
    formats: Sequence[str] = ("md", "tex", "docx"),
) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    profile = get_venue_profile(venue)
    portable = _materialize_images(document, output)
    files: Dict[str, str] = {}
    warnings: List[str] = []
    if "md" in formats:
        path = output / "manuscript.md"
        path.write_text(render_markdown(portable), encoding="utf-8")
        files["markdown"] = str(path)
    if "tex" in formats:
        path = output / "manuscript.tex"
        path.write_text(render_latex(portable, profile), encoding="utf-8")
        files["latex"] = str(path)
    if "html" in formats:
        path = output / "manuscript.html"
        path.write_text(_render_html(portable), encoding="utf-8")
        files["html"] = str(path)
    docx_path: Optional[Path] = None
    if "docx" in formats or "pdf" in formats:
        docx_path = output / "manuscript.docx"
        _render_docx(document, profile, docx_path)
        files["docx"] = str(docx_path)
    if "pdf" in formats and docx_path:
        pdf_path, warning = convert_docx_to_pdf(docx_path, output)
        if pdf_path:
            files["pdf"] = str(pdf_path)
        if warning:
            warnings.append(warning)
    return {
        "files": files,
        "warnings": warnings,
        "venue": profile,
        "template_status": profile.get("template_status"),
        "disclaimer": profile.get("disclaimer"),
    }
