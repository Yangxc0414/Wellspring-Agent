"""One-shot migration: bind methods to compositions and give each composition
a slot map (design/162). schema ese-method-registry-0.4 -> 0.5.

- per-method `composition_id`: which wiring the method instantiates;
- per-composition `slot_map`: element id -> governance slots it walks (the
  bridge between composition elements and the S0..META slots).
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "modules" / "method-registry" / "registry.json"

COMPOSITION_ID = {
    "systematic-literature-review": "confirmatory",
    "repository-mining": "exploratory",
    "controlled-experiment": "confirmatory",
    "quasi-experiment": "confirmatory",
    "benchmark-evaluation": "confirmatory",
    "case-study": "exploratory",
    "survey": "confirmatory",
    "design-science": "exploratory",
    "action-research": "exploratory",
    "ml-iterative-experiment": "exploratory"
}

SLOT_MAP = {
    "问题": ["S0"],
    "假设": ["S2-S3"],
    "方案": ["S4"],
    "证据": ["S1", "S1b", "S5"],
    "判定": ["S5b"],
    "图表": ["S6"],
    "写作": ["S8-S12"],
    "闭包": ["S13-S16"]
}


def main() -> None:
    with open(REGISTRY, "r", encoding="utf-8") as handle:
        registry = json.load(handle)

    assert registry["schema"] == "ese-method-registry-0.4", registry["schema"]
    composition_ids = {c["id"] for c in registry["compositions"]}
    wired_elements = {step["element"] for c in registry["compositions"] for step in c["wiring"]}

    registry["schema"] = "ese-method-registry-0.5"
    for composition in registry["compositions"]:
        # 按接线顺序给每个已接线要素绑定治理槽位（证据要素跨 S1 收集与 S5 执行）。
        composition["slot_map"] = {
            step["element"]: SLOT_MAP[step["element"]]
            for step in composition["wiring"]
            if step["element"] in SLOT_MAP
        }

    for method in registry["methods"]:
        binding = COMPOSITION_ID.get(method["id"])
        if binding is None:
            raise SystemExit("missing composition binding for " + method["id"])
        if binding not in composition_ids:
            raise SystemExit("binding references unknown composition: " + binding)
        method["composition_id"] = binding
        if not wired_elements:
            raise SystemExit("no wired elements")

    registry["composition_slot_maps_note"] = (
        "slot_map 桥接组合要素与治理槽位；证据要素跨 S1（收集）与 S5（执行）。"
    )

    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"bound {len(registry['methods'])} methods to compositions; slot_map on all; schema -> 0.5")


if __name__ == "__main__":
    main()
