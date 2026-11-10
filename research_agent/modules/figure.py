"""S6 figure module: build a deterministic scene and SVG with AstraDraw."""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ..adapters.astradraw_renderer import render_figure_svg
from ..adapters.svg_audit import audit_svg
from ..contracts import FigureArtifact, FigureEdge, FigureNode
from ..specs import ModuleSpec


class FigureError(RuntimeError):
    pass


@dataclass
class FigureRequest:
    title: str
    description: str
    nodes: List[FigureNode]
    edges: List[FigureEdge]
    style: str = "modern"
    width: int = 1440
    height: int = 300
    evidence_refs: List[str] = field(default_factory=list)
    run_id: str = ""


STYLE_SPECS = {
    "modern": {"font": "Microsoft YaHei", "radius": 10, "stroke": 2.0},
    "comic": {"font": "Comic Sans MS", "radius": 18, "stroke": 3.0},
    "roman": {"font": "Times New Roman", "radius": 2, "stroke": 2.2},
}

COLORS = {
    "literature": ("#EEF4FF", "#3B6FB6", "#1D3F6E"),
    "idea": ("#F3EEFF", "#7059B8", "#3F2F78"),
    "experiment": ("#EAF8F5", "#2F8A78", "#1D5B50"),
    "figure": ("#FFF2EC", "#C56856", "#7E3A2C"),
    "paper": ("#FFF7E8", "#B67A22", "#6E4A16"),
    "grant": ("#F2F4F8", "#667085", "#344054"),
}


def _safe_id(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return value or fallback


class FigureAgent:
    module_id = "figure"

    def __init__(self, spec: ModuleSpec):
        if spec.id != self.module_id:
            raise FigureError("spec id must be 'figure'")
        self.spec = spec

    def _run_id(self, provided: str) -> str:
        if provided:
            return provided
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return "FIG-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    def _layout(self, nodes: List[FigureNode]) -> Dict[str, Dict[str, int]]:
        by_level: Dict[int, List[FigureNode]] = {}
        for node in nodes:
            by_level.setdefault(node.level, []).append(node)
        positions = {}
        for level, group in by_level.items():
            for index, node in enumerate(group):
                positions[node.node_id] = {"x": 54 + level * 262, "y": 118 + index * 100, "w": 204, "h": 70}
        return positions

    def build_scene(self, request: FigureRequest) -> Dict[str, object]:
        if not request.nodes:
            raise FigureError("figure needs at least one node")
        node_ids = [node.node_id for node in request.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise FigureError("figure node ids must be unique")
        style_spec = STYLE_SPECS[request.style]
        positions = self._layout(request.nodes)
        max_level = max(node.level for node in request.nodes)
        max_rows = max(len([n for n in request.nodes if n.level == node.level]) for node in request.nodes)
        width = max(request.width, 54 + max_level * 262 + 204 + 54)
        height = max(request.height, 118 + max_rows * 100 + 70)
        objects: List[Dict[str, object]] = [
            {
                "id": "title", "type": "text", "role": "label", "x": 54, "y": 24,
                "width": width - 108, "height": 44, "text": request.title,
                "fontFamily": style_spec["font"], "fontSize": 30, "fill": "#172033", "bold": True,
            },
            {
                "id": "subtitle", "type": "text", "role": "label", "x": 54, "y": 74,
                "width": width - 108, "height": 30, "text": request.description,
                "fontFamily": style_spec["font"], "fontSize": 13, "fill": "#667085",
            },
        ]
        for node in request.nodes:
            pos = positions[node.node_id]
            fill, stroke, ink = COLORS.get(node.kind, COLORS["paper"])
            objects.append({
                "id": _safe_id(node.node_id, "node"),
                "type": "rect", "role": "module", "x": pos["x"], "y": pos["y"],
                "width": pos["w"], "height": pos["h"], "radius": style_spec["radius"],
                "fill": fill, "stroke": stroke, "strokeWidth": style_spec["stroke"],
            })
            objects.append({
                "id": _safe_id(node.node_id, "node") + "-label", "type": "text", "role": "label",
                "x": pos["x"] + 14, "y": pos["y"] + 16, "width": pos["w"] - 28, "height": pos["h"] - 26,
                "text": node.label, "fontFamily": style_spec["font"], "fontSize": 16,
                "fill": ink, "bold": True,
            })
        for edge_index, edge in enumerate(request.edges):
            if edge.source not in positions or edge.target not in positions:
                raise FigureError("edge references unknown node: %s -> %s" % (edge.source, edge.target))
            a, b = positions[edge.source], positions[edge.target]
            x1, y1 = a["x"] + a["w"], a["y"] + a["h"] / 2
            x2, y2 = b["x"], b["y"] + b["h"] / 2
            objects.append({
                "id": _safe_id("edge-" + edge.source + "-" + edge.target + "-%02d" % edge_index, "edge"),
                "type": "polyline", "role": "connector",
                "points": [[x1, y1], [x2, y2]],
                "stroke": "#8A96A8", "strokeWidth": 1.8,
                "dashed": bool(edge.dashed), "endArrow": True,
            })
            if edge.label:
                objects.append({
                    "id": _safe_id("edge-label-" + edge.source + "-" + edge.target + "-%02d" % edge_index, "edge-label"),
                    "type": "text", "role": "label", "x": (x1 + x2) / 2 - 44, "y": (y1 + y2) / 2 - 26,
                    "width": 88, "height": 20, "text": edge.label,
                    "fontFamily": style_spec["font"], "fontSize": 10, "fill": "#667085",
                })
        legend_y = height - 42
        legend = [("文献", "literature"), ("假设", "idea"), ("实验", "experiment"), ("图表", "figure"), ("稿件", "paper"), ("基金", "grant")]
        for index, (label, kind) in enumerate(legend):
            fill, stroke, _ = COLORS[kind]
            objects.append({
                "id": "legend-%d" % index, "type": "rect", "role": "legend",
                "x": 54 + index * 92, "y": legend_y, "width": 12, "height": 12,
                "radius": 3, "fill": fill, "stroke": stroke, "strokeWidth": 1.2,
            })
            objects.append({
                "id": "legend-label-%d" % index, "type": "text", "role": "label",
                "x": 72 + index * 92, "y": legend_y - 3, "width": 60, "height": 20,
                "text": label, "fontFamily": style_spec["font"], "fontSize": 10, "fill": "#667085",
            })
        return {
            "schema_version": 1,
            "id": _safe_id(request.run_id or "research-agent-figure", "figure"),
            "component": "research-agent-module-graph",
            "style": request.style,
            "width": width,
            "height": height,
            "scientific_notes": [
                "Schematic module graph; not an experimental result and not a data plot.",
                "Node positions and colors are illustrative; they do not encode measured effects.",
                "Evidence references: " + (", ".join(request.evidence_refs) if request.evidence_refs else "none supplied"),
            ],
            "objects": objects,
        }

    def run(self, request: FigureRequest) -> FigureArtifact:
        if self.spec.status in ("revoked", "deprecated"):
            raise FigureError("module spec status is %s; refusing to run" % self.spec.status)
        if not request.title.strip():
            raise FigureError("figure title is required")
        if request.style not in ("comic", "roman", "modern"):
            raise FigureError("style must be comic, roman or modern")
        figure_id = self._run_id(request.run_id)
        scene = self.build_scene(request)
        provenance = {
            "generator": "research_agent.figure",
            "spec_version": self.spec.version,
            "astradraw_source": "research_agent/vendor/astradraw",
            "style": request.style,
            "evidence_refs": list(request.evidence_refs),
            "schematic": True,
        }
        description = request.description + "（示意图，不是实验结果）"
        renderer_present = True
        try:
            svg, audit = render_figure_svg(scene, request.title, description, provenance)
        except FileNotFoundError as exc:
            # a missing optional third-party renderer must not invalidate the run; it
            # removes the picture, and the manifest says so instead of staying silent
            svg, renderer_present = "", False
            audit = {
                "ok": False,
                "errors": ["astradraw_renderer_missing"],
                "notes": [str(exc)],
            }
        if renderer_present and not audit.get("ok"):
            raise FigureError("SVG audit failed: " + "; ".join(audit.get("errors", [])))
        scene_text = json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        manifest = {
            "figure_id": figure_id,
            "title": request.title,
            "schematic": True,
            "kind": "module_graph",
            "style": request.style,
            "scene_sha256": hashlib.sha256(scene_text.encode("utf-8")).hexdigest(),
            "svg_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest() if svg else "",
            "renderer_available": renderer_present,
            "evidence_refs": list(request.evidence_refs),
            "provenance": provenance,
            "audit": audit,
        }
        return FigureArtifact(
            figure_id=figure_id,
            scene=scene,
            svg=svg,
            manifest=manifest,
            audit=audit,
        )


def build_result_figure(
    capsule: Dict[str, object],
    output_dir: Path,
    evidence_refs: List[str],
    figure_id: str = "",
) -> Dict[str, object]:
    """Render a data-backed metric chart; not a schematic figure."""
    metrics = capsule.get("metrics_by_seed") or []
    if not metrics:
        raise FigureError("result figure needs per-seed metrics")
    method_key = "r2" if capsule.get("metric_name") == "r2" else "accuracy"
    baseline_key = "baseline_r2" if method_key == "r2" else None
    values = [float(item[method_key]) for item in metrics]
    if baseline_key:
        values.extend(float(item[baseline_key]) for item in metrics if baseline_key in item)
    low = min(min(values), 0.0) - 0.05
    high = max(max(values), 1.0 if method_key == "accuracy" else 0.0) + 0.05
    if high <= low:
        high = low + 1.0

    width, height = 840, 380
    left, top, plot_w, plot_h = 80, 70, 680, 230
    group_w = plot_w / max(1, len(metrics))
    bars = []
    labels = []
    for index, item in enumerate(metrics):
        center = left + group_w * (index + 0.5)
        value = float(item[method_key])
        bar_h = max(1.0, (value - low) / (high - low) * plot_h)
        bars.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#3B6FB6"/>'
            % (center - 26, top + plot_h - bar_h, 24, bar_h)
        )
        if baseline_key and baseline_key in item:
            base = float(item[baseline_key])
            base_h = max(1.0, (base - low) / (high - low) * plot_h)
            bars.append(
                '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#98A2B3"/>'
                % (center + 2, top + plot_h - base_h, 24, base_h)
            )
        labels.append(
            '<text x="%.1f" y="%d" text-anchor="middle" font-family="Arial" font-size="12" fill="#475467">seed %s</text>'
            % (center, top + plot_h + 22, item.get("seed"))
        )
    axis = (
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#344054"/>'
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#344054"/>'
        '<text x="%d" y="%d" text-anchor="end" font-family="Arial" font-size="12" fill="#475467">%.2f</text>'
        '<text x="%d" y="%d" text-anchor="end" font-family="Arial" font-size="12" fill="#475467">%.2f</text>'
        % (
            left, top, left, top + plot_h, left, top + plot_h, left + plot_w, top + plot_h,
            left - 8, top + 4, high, left - 8, top + plot_h, low,
        )
    )
    title = "Result: %s / %s" % (capsule.get("dataset_id", "dataset"), capsule.get("metric_name", "metric"))
    desc = (
        "Data-backed result figure from RunCapsule %s; seeds %s. "
        "Not peer-reviewed and not a schematic."
        % (capsule.get("run_id", ""), capsule.get("seeds", []))
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="fig-title fig-desc">'
        '<title id="fig-title">%s</title><desc id="fig-desc">%s</desc>'
        '<rect width="100%%" height="100%%" fill="#FFFFFF"/>'
        '%s%s%s'
        '</svg>'
    ) % (
        width, height, width, height,
        _escape(title), _escape(desc), axis, "".join(bars), "".join(labels),
    )
    report = audit_svg(svg)
    if not report["ok"]:
        raise FigureError("result SVG audit failed: %s" % report["errors"])
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / "result-figure.svg"
    with open(str(svg_path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)
    fid = figure_id or "FIG-RESULT-" + _safe_id(str(capsule.get("run_id", "run")), "run")
    manifest = {
        "figure_id": fid,
        "kind": "result_data",
        "schematic": False,
        "run_id": capsule.get("run_id"),
        "dataset_id": capsule.get("dataset_id"),
        "metric_name": capsule.get("metric_name"),
        "seeds": capsule.get("seeds"),
        "method_series": method_key,
        "baseline_series": baseline_key,
        "svg_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        "data_sha256": hashlib.sha256(json.dumps(metrics, sort_keys=True).encode("utf-8")).hexdigest(),
        "evidence_refs": list(evidence_refs),
        "audit": report,
    }
    manifest_path = output_dir / "result-figure.manifest.json"
    with open(str(manifest_path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {
        "figure_id": fid, "svg": svg, "manifest": manifest,
        "paths": {"svg": str(svg_path), "manifest": str(manifest_path)},
    }


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
