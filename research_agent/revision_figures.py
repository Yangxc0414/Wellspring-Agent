"""Generate data-backed result figures for manuscript revision."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .revision_io import (
    RevisionIOError,
    _as_number,
    _filter_rows,
    _find_table,
    _row_value,
    sha256_file,
    sha256_text,
)
from .revision_types import DataTable


SPEC_KEYS = {
    "id", "type", "table", "x", "y", "series", "agg", "where",
    "title", "caption", "xlabel", "ylabel", "insert_after_heading", "dpi",
}


def load_figure_specs(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RevisionIOError("cannot read figure spec: %s" % exc)
    figures = data.get("figures") if isinstance(data, dict) else data
    if not isinstance(figures, list):
        raise RevisionIOError("figure spec must contain a figures list")
    normalized = []
    for index, item in enumerate(figures):
        if not isinstance(item, dict):
            raise RevisionIOError("figure #%d must be an object" % index)
        figure_id = str(item.get("id") or "fig%d" % (index + 1)).strip()
        # a field name the loader does not read used to disappear silently, so `"kind": "line"`
        # rendered a bar chart and the figure looked authored
        unknown = sorted(str(key) for key in set(item) - SPEC_KEYS)
        if unknown:
            raise RevisionIOError(
                "figure %s uses unknown field(s): %s; known fields are: %s"
                % (figure_id, ", ".join(unknown), ", ".join(sorted(SPEC_KEYS)))
            )
        figure_type = str(item.get("type") or "bar").strip().lower()
        if figure_type not in ("bar", "line"):
            raise RevisionIOError("figure type must be bar or line: " + figure_type)
        normalized.append(
            {
                "id": figure_id,
                "type": figure_type,
                "table": str(item.get("table") or ""),
                "x": str(item.get("x") or ""),
                "y": str(item.get("y") or ""),
                "series": str(item.get("series") or ""),
                "agg": str(item.get("agg") or "mean").strip().lower(),
                "where": item.get("where") if isinstance(item.get("where"), dict) else {},
                "title": str(item.get("title") or figure_id),
                "caption": str(item.get("caption") or item.get("title") or figure_id),
                "xlabel": str(item.get("xlabel") or item.get("x") or ""),
                "ylabel": str(item.get("ylabel") or item.get("y") or ""),
                "insert_after_heading": str(item.get("insert_after_heading") or ""),
                "dpi": int(item.get("dpi", 300)),
                "spec": item,
            }
        )
    return normalized


def _aggregate(values: List[float], agg: str) -> float:
    if not values:
        return 0.0
    if agg == "sum":
        return sum(values)
    if agg == "count":
        return float(len(values))
    if agg == "max":
        return max(values)
    if agg == "min":
        return min(values)
    return sum(values) / len(values)


def _series_data(
    spec: Dict[str, Any], table: DataTable
) -> Tuple[Dict[str, List[float]], List[str], List[str]]:
    rows = _filter_rows(table.rows, spec.get("where") or {})
    x_col = spec.get("x", "")
    y_col = spec.get("y", "")
    series_col = spec.get("series", "")
    if not x_col or not y_col:
        raise RevisionIOError("figure %s needs x and y columns" % spec.get("id"))
    grouped: Dict[str, Dict[str, List[float]]] = {}
    x_order: List[str] = []
    for row in rows:
        x = _row_value(row, x_col)
        y = _as_number(_row_value(row, y_col))
        if not x or y is None:
            continue
        if x not in x_order:
            x_order.append(x)
        if series_col:
            series_name = _row_value(row, series_col) or "series"
            grouped.setdefault(series_name, {}).setdefault(x, []).append(y)
        else:
            grouped.setdefault("value", {}).setdefault(x, []).append(y)
    if not x_order:
        raise RevisionIOError("figure %s has no numeric rows" % spec.get("id"))
    try:
        x_sorted = sorted(x_order, key=lambda value: float(value))
    except ValueError:
        x_sorted = list(x_order)
    for series_values in grouped.values():
        for x in list(series_values.keys()):
            series_values[x] = [_aggregate(series_values[x], spec.get("agg", "mean"))]
    return {name: values for name, values in grouped.items()}, x_sorted, list(grouped.keys())


def _font_setup() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def generate_figures(
    specs: Sequence[Dict[str, Any]],
    tables: List[DataTable],
    output_dir: Path,
) -> Dict[str, Any]:
    if not specs:
        return {
            "schema_version": "revision-figure-manifest-0.1",
            "figures": [],
            "warnings": [],
            "boundary": "figures are data-backed, not peer-reviewed results",
        }
    _font_setup()
    import matplotlib.pyplot as plt

    target = Path(output_dir) / "figures"
    target.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for spec in specs:
        try:
            table = _find_table(tables, spec.get("table", ""))
            series, x_order, series_names = _series_data(spec, table)
        except RevisionIOError as exc:
            warnings.append("%s: %s" % (spec.get("id"), exc))
            continue
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        width = 0.8 / max(1, len(series_names))
        if spec["type"] == "bar":
            positions = list(range(len(x_order)))
            for index, name in enumerate(series_names):
                values_by_x = series[name]
                values = [values_by_x.get(x, [0.0])[0] for x in x_order]
                offsets = [pos - 0.4 + width / 2 + index * width for pos in positions]
                ax.bar(offsets, values, width=width, label=name if spec.get("series") else None)
            ax.set_xticks(list(range(len(x_order))))
            ax.set_xticklabels(x_order)
        else:
            for name in series_names:
                values_by_x = series[name]
                values = [values_by_x.get(x, [0.0])[0] for x in x_order]
                ax.plot(x_order, values, marker="o", label=name if spec.get("series") else None)
        ax.set_title(spec.get("title", spec["id"]))
        ax.set_xlabel(spec.get("xlabel", spec.get("x")))
        ax.set_ylabel(spec.get("ylabel", spec.get("y")))
        ax.grid(axis="y", alpha=0.25)
        if spec.get("series"):
            ax.legend()
        fig.tight_layout()
        png = target / (spec["id"] + ".png")
        svg = target / (spec["id"] + ".svg")
        fig.savefig(str(png), dpi=spec.get("dpi", 300))
        fig.savefig(str(svg))
        plt.close(fig)
        used_rows = _filter_rows(table.rows, spec.get("where") or {})
        manifest.append(
            {
                "figure_id": spec["id"],
                "type": spec["type"],
                "title": spec.get("title"),
                "caption": spec.get("caption"),
                "insert_after_heading": spec.get("insert_after_heading", ""),
                "table": table.name,
                "x": spec.get("x"),
                "y": spec.get("y"),
                "series": spec.get("series"),
                "agg": spec.get("agg"),
                "where": spec.get("where") or {},
                "data_sha256": sha256_text(json.dumps(used_rows, sort_keys=True, ensure_ascii=False)),
                "spec_sha256": sha256_text(json.dumps(spec.get("spec") or spec, sort_keys=True, ensure_ascii=False)),
                "png": str(png),
                "svg": str(svg),
                "output_sha256": sha256_file(png),
                "schematic": False,
                "boundary": "data-backed figure generated from a user-provided table; not peer-reviewed",
            }
        )
    return {
        "schema_version": "revision-figure-manifest-0.1",
        "figures": manifest,
        "warnings": warnings,
        "boundary": "figures are data-backed, not peer-reviewed results",
    }
