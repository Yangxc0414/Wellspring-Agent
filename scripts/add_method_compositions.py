"""One-shot migration: lift the port model and reference compositions into the
method registry (design/156). schema ese-method-registry-0.3 -> 0.4.

Adds top-level `elements` (typed ports: what each governance element consumes
/ produces — the INVARIANT meta-model) and `compositions` (two reference
wirings — the VARIABLE layer). The order of a composition is the result of
its wiring; the loader will fail-closed on illegal wirings (port matching).
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "modules" / "method-registry" / "registry.json"

ELEMENTS = [
    {"id": "问题", "label": "研究问题", "input_kinds": [],
     "outputs": [{"consumes": None, "produces": "研究问题"}], "human": False},
    {"id": "假设", "label": "问题与假设", "input_kinds": ["研究问题", "RunCapsule + EA"],
     "outputs": [
         {"consumes": "研究问题", "produces": "候选假设（可判别）"},
         {"consumes": "RunCapsule + EA", "produces": "提炼式假设（事后）"}],
     "human": True},
    {"id": "方案", "label": "研究方案（设计冻结）", "input_kinds": ["候选假设（可判别）", "研究问题"],
     "outputs": [
         {"consumes": "候选假设（可判别）", "produces": "判别式协议"},
         {"consumes": "研究问题", "produces": "数据收集协议"}],
     "human": True},
    {"id": "证据", "label": "证据生产（执行）", "input_kinds": ["判别式协议", "数据收集协议"],
     "outputs": [
         {"consumes": "判别式协议", "produces": "RunCapsule + EA"},
         {"consumes": "数据收集协议", "produces": "RunCapsule + EA"}],
     "human": False},
    {"id": "判定", "label": "断言与签核", "input_kinds": ["RunCapsule + EA"],
     "outputs": [{"consumes": "RunCapsule + EA", "produces": "ClaimRecord"}], "human": True},
    {"id": "图表", "label": "结果图表", "input_kinds": ["RunCapsule + EA"],
     "outputs": [{"consumes": "RunCapsule + EA", "produces": "图 manifest"}], "human": False},
    {"id": "写作", "label": "写作与评审", "input_kinds": ["ClaimRecord", "图 manifest"],
     "outputs": [{"consumes": "ClaimRecord", "produces": "稿件绑定"}], "human": True},
    {"id": "闭包", "label": "闭包与导出签核", "input_kinds": ["ClaimRecord", "RunCapsule + EA"],
     "outputs": [{"consumes": "ClaimRecord", "produces": "closure + 导出"}], "human": True},
    {"id": "经验", "label": "经验与自改进", "input_kinds": ["closure + 导出"],
     "outputs": [{"consumes": "closure + 导出", "produces": "任务反馈"}], "human": True},
]

COMPOSITIONS = [
    {
        "id": "confirmatory",
        "label": "验证式组合",
        "sub": "假设在前：方案消费假设，成为判别式协议",
        "wiring": [
            {"element": "问题", "consumes": None},
            {"element": "假设", "consumes": "研究问题"},
            {"element": "方案", "consumes": "候选假设（可判别）"},
            {"element": "证据", "consumes": "判别式协议"},
            {"element": "判定", "consumes": "RunCapsule + EA"},
            {"element": "图表", "consumes": "RunCapsule + EA"},
            {"element": "写作", "consumes": "ClaimRecord"},
            {"element": "闭包", "consumes": "ClaimRecord"},
            {"element": "经验", "consumes": "closure + 导出"}
        ]
    },
    {
        "id": "exploratory",
        "label": "探索式组合",
        "sub": "证据在前：方案只消费问题（数据收集设计），假设从证据中提炼",
        "wiring": [
            {"element": "问题", "consumes": None},
            {"element": "方案", "consumes": "研究问题"},
            {"element": "证据", "consumes": "数据收集协议"},
            {"element": "假设", "consumes": "RunCapsule + EA"},
            {"element": "判定", "consumes": "RunCapsule + EA"},
            {"element": "图表", "consumes": "RunCapsule + EA"},
            {"element": "写作", "consumes": "ClaimRecord"},
            {"element": "闭包", "consumes": "ClaimRecord"},
            {"element": "经验", "consumes": "closure + 导出"}
        ]
    }
]


def main() -> None:
    with open(REGISTRY, "r", encoding="utf-8") as handle:
        registry = json.load(handle)

    assert registry["schema"] == "ese-method-registry-0.3", registry["schema"]
    registry["schema"] = "ese-method-registry-0.4"
    registry["elements"] = ELEMENTS
    registry["compositions"] = COMPOSITIONS

    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"elements {len(ELEMENTS)}; compositions {len(COMPOSITIONS)}; schema -> ese-method-registry-0.4")


if __name__ == "__main__":
    main()
