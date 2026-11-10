"""Deterministic sentence splitter shared by fixture, local PDF and real-corpus runs.

PDF text usually arrives hard-wrapped: a sentence can span several lines and a
line can start mid-sentence. Splitting on newlines produces fragments that look
like evidence but are not readable claims. Normalisation joins wrapped lines
before sentence splitting, while keeping paragraph and heading boundaries.
"""

import re
from typing import Any, Dict, List, Tuple

from ..contracts import SourceHit, Span

SENTENCE_RE = re.compile(r"[^。！？.!?\n]+[。！？.!?]?")
HYPHEN_BREAK_RE = re.compile(r"(?<=[A-Za-z])[-‐]\s*\n\s*(?=[a-z])")
INLINE_ABBREVIATIONS = (
    "e.g.", "i.e.", "et al.", "cf.", "vs.", "fig.", "figs.", "eq.", "eqs.",
    "no.", "nos.", "dr.", "prof.", "approx.", "ref.", "refs.", "sec.", "al.",
)
LINE_JOIN_ENDINGS = (",", "-", "/", "(", ":", ";", "的", "和", "与", "及", "在", "对", "为", "是")


def _strip_invisibles(text: str) -> str:
    return text.replace("\u200b", "").replace("\ufeff", "")


def _should_join_lines(previous: str, line: str) -> bool:
    previous = previous.rstrip()
    if not previous or not line:
        return False
    if previous.endswith((".", "!", "?", "。", "！", "？")):
        return False
    if line[:1].islower():
        return True
    return previous.endswith(LINE_JOIN_ENDINGS)


def normalize_section_text(text: str) -> str:
    text = _strip_invisibles(str(text or ""))
    text = HYPHEN_BREAK_RE.sub("", text)
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        if lines and not lines[-1] and len(lines) >= 2 and line[:1].islower():
            lines.pop()
            lines[-1] = lines[-1].rstrip() + " " + line
        elif lines and lines[-1] and _should_join_lines(lines[-1], line):
            lines[-1] = lines[-1].rstrip() + " " + line
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _ends_with_inline_abbreviation(text: str) -> bool:
    lowered = text.rstrip().lower()
    return any(lowered.endswith(token) for token in INLINE_ABBREVIATIONS)


def _should_join_sentences(previous: str, current: str) -> bool:
    previous = previous.rstrip()
    current = current.lstrip()
    if not previous or not current:
        return False
    if current[:1].islower():
        return True
    if _ends_with_inline_abbreviation(previous):
        return True
    if re.search(r"\d\.$", previous) and current[:1].isdigit():
        return True
    if re.search(r"\b[A-Z]\.$", previous):
        return True
    return previous.endswith((",", ";", ":"))


def _sentence_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for match in SENTENCE_RE.finditer(text):
        start, end = match.span()
        if not text[start:end].strip():
            continue
        if ranges:
            previous_start, _ = ranges[-1]
            if _should_join_sentences(text[previous_start : ranges[-1][1]], text[start:end]):
                ranges[-1] = (previous_start, end)
                continue
        ranges.append((start, end))
    return ranges


class SimpleParser:
    def __init__(self, max_spans_per_source: int = 8):
        self.max_spans_per_source = max_spans_per_source

    def spans(self, source: SourceHit, document: Dict[str, Any]) -> List[Span]:
        if not source.full_text:
            return []
        spans: List[Span] = []
        for section_index, section in enumerate(document.get("sections", [])):
            text = normalize_section_text(section.get("text", ""))
            section_name = str(section.get("name", "section-%d" % section_index))
            for sentence_index, (start, end) in enumerate(_sentence_ranges(text)):
                sentence = re.sub(r"\s+", " ", text[start:end]).strip()
                if len(sentence) < 12:
                    continue
                spans.append(
                    Span(
                        span_id="%s-S%02d-%02d" % (source.source_id, section_index + 1, sentence_index + 1),
                        source_id=source.source_id,
                        section=section_name,
                        text=sentence,
                        start=start,
                        end=end,
                        fixture=source.fixture,
                        page=section.get("page") if isinstance(section.get("page"), int) else None,
                    )
                )
                if len(spans) >= self.max_spans_per_source:
                    return spans
        return spans
