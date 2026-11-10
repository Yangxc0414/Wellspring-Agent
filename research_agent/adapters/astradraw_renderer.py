"""Adapter around the vendored AstraDraw scene renderer.

We import the upstream `build_components.render_svg` without modifying it. The
adapter owns only post-processing needed by our framework (root title/desc,
role=img, provenance metadata).
"""

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

from .svg_audit import audit_svg

_RENDERER = None
_RENDERER_PATH = Path(__file__).resolve().parents[1] / "vendor" / "astradraw" / "scripts" / "build_components.py"


def renderer_available() -> bool:
    """Whether the vendored third-party renderer is present.

    The schematic is advisory output, so callers must be able to degrade instead of
    failing a whole run when a release copy ships without the vendored scripts.
    """
    return _RENDERER_PATH.is_file()


def _load_renderer():
    global _RENDERER
    if _RENDERER is None:
        if not _RENDERER_PATH.is_file():
            raise FileNotFoundError("AstraDraw renderer not found: " + str(_RENDERER_PATH))
        spec = importlib.util.spec_from_file_location("research_agent_astradraw_build", str(_RENDERER_PATH))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _RENDERER = module
    return _RENDERER


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _decorate(svg: str, title: str, description: str, provenance: Dict[str, Any]) -> str:
    marker = "<svg "
    if marker not in svg:
        raise ValueError("renderer did not return an <svg> root")
    head = (
        '<svg role="img" aria-labelledby="fig-title fig-desc" '
    )
    svg = svg.replace(marker, head, 1)
    insert_at = svg.find(">") + 1
    meta = _xml_escape(json.dumps(provenance, ensure_ascii=False, sort_keys=True))
    block = (
        '\n<title id="fig-title">%s</title>'
        '\n<desc id="fig-desc">%s</desc>'
        '\n<metadata id="fig-provenance">%s</metadata>'
    ) % (_xml_escape(title), _xml_escape(description), meta)
    return svg[:insert_at] + block + svg[insert_at:]


def render_figure_svg(scene: Dict[str, Any], title: str, description: str, provenance: Dict[str, Any]) -> tuple:
    renderer = _load_renderer()
    raw = renderer.render_svg(scene)
    svg = _decorate(raw, title, description, provenance)
    audit = audit_svg(svg)
    return svg, audit
