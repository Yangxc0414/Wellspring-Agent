"""Render AstraDraw scene files and bundled template scenes.

The upstream AstraDraw folder is never modified. The renderer is imported from
the vendored copy through the existing adapter; this module only resolves a
scene, writes artifacts, audits SVG and optionally converts a PNG preview.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .adapters.astradraw_renderer import render_figure_svg
from .paths import REPO_ROOT
from .storage import write_json_atomic

FIGURE_SCHEMA = "astradraw-render-0.1"
BOUNDARY = (
    "AstraDraw templates are visual/layout priors only; the output is a schematic, "
    "not a data plot, not evidence, and not a publication approval"
)
VENDOR_ROOT = REPO_ROOT / "research_agent" / "vendor" / "astradraw"
TEMPLATES = {
    "calm-method": "output/calm-method/calm-method-final.scene.json",
    "role-guided-search": "examples/role-guided-search/overview.scene.json",
    "self-forcing": "examples/self-forcing/overview.scene.json",
    "framework-example": "examples/framework/conditional-flow.scene.json",
    "survey-framework": "output/survey-framework/survey-framework-print.scene.json",
    "calm-survey": "output/calm-survey/overview-v2.scene.json",
    "tracerl-method": "output/tracerl-method/tracerl-method-paper.scene.json",
}


class FigureWorkflowError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(value or "").strip()).strip("-")
    return cleaned[:60] or "figure"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _load_scene(path: Path) -> Dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FigureWorkflowError("scene file does not exist: " + str(source))
    try:
        scene = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FigureWorkflowError("cannot read scene JSON: %s" % exc)
    if not isinstance(scene, dict):
        raise FigureWorkflowError("scene must be a JSON object")
    if scene.get("schema_version") != 1:
        raise FigureWorkflowError("scene schema_version must be 1")
    objects = scene.get("objects")
    if not isinstance(objects, list) or not objects:
        raise FigureWorkflowError("scene must contain a non-empty objects list")
    if not isinstance(scene.get("width"), (int, float)) or not isinstance(scene.get("height"), (int, float)):
        raise FigureWorkflowError("scene needs numeric width and height")
    return scene


def list_templates() -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for template_id, relative in TEMPLATES.items():
        path = VENDOR_ROOT / relative
        try:
            scene = _load_scene(path)
        except FigureWorkflowError as exc:
            warnings.append("%s: %s" % (template_id, exc))
            continue
        entries.append(
            {
                "id": template_id,
                "scene_id": scene.get("id"),
                "component": scene.get("component"),
                "style": scene.get("style"),
                "width": scene.get("width"),
                "height": scene.get("height"),
                "objects": len(scene.get("objects") or []),
                "schematic": True,
                "source": "research_agent/vendor/astradraw/" + relative,
            }
        )
    return {
        "schema_version": "astradraw-template-catalog-0.1",
        "templates": entries,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }


def template_path(template_id: str) -> Path:
    relative = TEMPLATES.get(str(template_id or "").strip())
    if not relative:
        raise FigureWorkflowError("unknown AstraDraw template: " + str(template_id))
    path = VENDOR_ROOT / relative
    if not path.is_file():
        raise FigureWorkflowError("vendored template is missing: " + str(path))
    return path


def _convert_svg_to_png(svg_path: Path, output_dir: Path) -> tuple:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None, "LibreOffice/soffice not found; SVG created, PNG skipped"
    profile = Path(tempfile.mkdtemp(prefix="astradraw-png-"))
    command = [
        soffice, "--headless", "--norestore",
        "-env:UserInstallation=file:///" + profile.as_posix(),
        "--convert-to", "png", "--outdir", str(output_dir), str(svg_path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(str(profile), ignore_errors=True)
        return None, "PNG conversion failed: %s" % exc
    shutil.rmtree(str(profile), ignore_errors=True)
    target = output_dir / (svg_path.stem + ".png")
    if completed.returncode != 0 or not target.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-300:]
        return None, "PNG conversion failed: " + (detail or "unknown error")
    return target, ""


def render_scene(
    scene_path: Path,
    output_dir: Path,
    title: str = "",
    description: str = "",
    output_name: str = "",
    formats: Sequence[str] = ("svg", "png"),
    template_id: str = "",
) -> Dict[str, Any]:
    formats = [str(item).lower() for item in formats]
    invalid = [item for item in formats if item not in ("svg", "png")]
    if invalid:
        raise FigureWorkflowError("unsupported figure formats: " + ", ".join(invalid))
    scene = _load_scene(Path(scene_path))
    scene_hash = _sha256_json(scene)
    figure_title = str(title or scene.get("id") or "research figure").strip()
    figure_description = str(
        description or "; ".join(scene.get("scientific_notes") or []) or "AstraDraw schematic"
    ).strip()
    name = _slug(output_name or str(scene.get("id") or "figure"))
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FigureWorkflowError(
            "figure output directory is not empty; choose a new name or directory: " + str(output)
        )
    output.mkdir(parents=True, exist_ok=True)
    figure_id = "FIG-" + name + "-" + scene_hash[:8]
    scene_output = output / (name + ".scene.json")
    scene_text = json.dumps(scene, ensure_ascii=False, indent=2) + "\n"
    with open(str(scene_output), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(scene_text)
    provenance = {
        "generator": "research_agent.figure_workflow",
        "astradraw_source": "research_agent/vendor/astradraw",
        "template_id": template_id or None,
        "scene_sha256": scene_hash,
        "schematic": True,
        "notice": BOUNDARY,
    }
    svg, audit = render_figure_svg(scene, figure_title, figure_description, provenance)
    if not audit.get("ok"):
        raise FigureWorkflowError("SVG audit failed: " + "; ".join(audit.get("errors") or []))
    svg_path = output / (name + ".svg")
    with open(str(svg_path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)
    audit_path = output / (name + ".audit.json")
    write_json_atomic(audit_path, audit)
    warnings: List[str] = []
    png_path = None
    if "png" in formats:
        png_path, warning = _convert_svg_to_png(svg_path, output)
        if warning:
            warnings.append(warning)
    manifest = {
        "schema_version": FIGURE_SCHEMA,
        "figure_id": figure_id,
        "title": figure_title,
        "description": figure_description,
        "schematic": True,
        "kind": "astradraw_scene",
        "renderer": "astradraw",
        "data_result_plot": False,
        "template_id": template_id or None,
        "source_scene": str(scene_path),
        "source_scene_sha256": _sha256_file(Path(scene_path)),
        "scene_sha256": scene_hash,
        "svg_sha256": _sha256_file(svg_path),
        "png_sha256": _sha256_file(png_path) if png_path else "",
        "object_count": len(scene.get("objects") or []),
        "width": scene.get("width"),
        "height": scene.get("height"),
        "files": {
            "scene": str(scene_output),
            "svg": str(svg_path),
            "audit": str(audit_path),
            "png": str(png_path) if png_path else "",
        },
        "audit": audit,
        "provenance": provenance,
        "warnings": warnings,
        "created_at": _now(),
        "boundary": BOUNDARY,
    }
    manifest_path = output / (name + ".manifest.json")
    write_json_atomic(manifest_path, manifest)
    return {
        "schema_version": FIGURE_SCHEMA,
        "status": "rendered",
        "figure_id": figure_id,
        "output_dir": str(output),
        "files": manifest["files"],
        "manifest": str(manifest_path),
        "audit_status": "pass" if audit.get("ok") else "fail",
        "warnings": warnings,
        "boundary": BOUNDARY,
    }


def render_template(
    template_id: str,
    output_dir: Path,
    title: str = "",
    description: str = "",
    output_name: str = "",
    formats: Sequence[str] = ("svg", "png"),
) -> Dict[str, Any]:
    path = template_path(template_id)
    return render_scene(
        scene_path=path,
        output_dir=output_dir,
        title=title,
        description=description,
        output_name=output_name or template_id,
        formats=formats,
        template_id=template_id,
    )
