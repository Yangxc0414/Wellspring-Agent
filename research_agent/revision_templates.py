"""Structural venue profiles for existing-manuscript revision.

These are working typographic profiles, not publisher-official templates.
"""

from typing import Any, Dict, List


VENUE_PROFILES: Dict[str, Dict[str, Any]] = {
    "zh_core_journal": {
        "id": "zh_core_journal",
        "label": "中文核心期刊通用工作稿",
        "language": "zh",
        "page_width_cm": 21.0,
        "page_height_cm": 29.7,
        "margin_top_cm": 2.4,
        "margin_bottom_cm": 2.4,
        "margin_left_cm": 2.4,
        "margin_right_cm": 2.4,
        "body_pt": 10.5,
        "heading_pt": 12.0,
        "title_pt": 18.0,
        "reference_pt": 9.0,
        "figure_width_cm": 15.5,
        "required_sections": [
            ["摘要", "abstract"],
            ["引言", "introduction"],
            ["相关工作", "related work", "文献综述"],
            ["方法", "method", "方法设计"],
            ["实验", "experiment", "实验设计"],
            ["结果", "result", "结果与分析"],
            ["讨论", "discussion"],
            ["结论", "conclusion"],
        ],
        "template_status": "working_profile_not_official",
        "disclaimer": "通用中文期刊工作排版；投稿前必须替换为目标期刊官方模板并人工复核。",
    },
    "software_journal": {
        "id": "software_journal",
        "label": "软件学报风格工作稿",
        "language": "zh",
        "page_width_cm": 18.4,
        "page_height_cm": 26.0,
        "margin_top_cm": 1.0,
        "margin_bottom_cm": 2.2,
        "margin_left_cm": 1.45,
        "margin_right_cm": 1.45,
        "body_pt": 9.0,
        "heading_pt": 10.5,
        "title_pt": 18.0,
        "reference_pt": 7.5,
        "figure_width_cm": 16.0,
        "required_sections": [
            ["摘要", "abstract"],
            ["引言", "introduction"],
            ["相关工作", "related work"],
            ["方法", "method"],
            ["实验", "experiment"],
            ["结果", "result"],
            ["结论", "conclusion"],
        ],
        "template_status": "working_profile_not_official",
        "disclaimer": "按公开样例近似的工作排版，不是《软件学报》官方模板；必须以官网最新模板复核。",
    },
    "computer_journal": {
        "id": "computer_journal",
        "label": "计算机学报风格工作稿",
        "language": "zh",
        "page_width_cm": 21.0,
        "page_height_cm": 29.7,
        "margin_top_cm": 2.2,
        "margin_bottom_cm": 2.2,
        "margin_left_cm": 2.0,
        "margin_right_cm": 2.0,
        "body_pt": 10.5,
        "heading_pt": 12.0,
        "title_pt": 18.0,
        "reference_pt": 9.0,
        "figure_width_cm": 16.0,
        "required_sections": [
            ["摘要", "abstract"],
            ["引言", "introduction"],
            ["相关工作", "related work"],
            ["方法", "method"],
            ["实验", "experiment"],
            ["结果", "result"],
            ["讨论", "discussion"],
            ["结论", "conclusion"],
        ],
        "template_status": "working_profile_not_official",
        "disclaimer": "计算机学报风格的工作排版；不是官方模板，投稿前必须按官网要求复核。",
    },
}


def get_venue_profile(name: str) -> Dict[str, Any]:
    key = str(name or "zh_core_journal").strip().lower()
    profile = VENUE_PROFILES.get(key)
    if profile is None:
        raise ValueError(
            "unknown venue profile: %s (choose %s)"
            % (name, ", ".join(sorted(VENUE_PROFILES)))
        )
    return dict(profile)


def section_aliases(group: List[str]) -> List[str]:
    return [str(item).strip().lower() for item in group if str(item).strip()]


def missing_required_sections(
    headings: List[str], profile: Dict[str, Any]
) -> List[List[str]]:
    lowered = [str(item).strip().lower() for item in headings]
    missing: List[List[str]] = []
    for group in profile.get("required_sections") or []:
        aliases = section_aliases(group)
        if not any(any(alias in heading for alias in aliases) for heading in lowered):
            missing.append(list(group))
    return missing


def profile_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": profile.get("id"),
        "label": profile.get("label"),
        "template_status": profile.get("template_status"),
        "body_pt": profile.get("body_pt"),
        "reference_pt": profile.get("reference_pt"),
        "disclaimer": profile.get("disclaimer"),
    }
