# -*- coding: utf-8 -*-
"""Generate the Wellspring-Agent four-layer architecture scene (paper-method palette).

Innovation callouts: 1=span-only 2=human gates outside architecture
3=lineage stale loop 4=lease-gated RSI. Structural source: ARCHITECTURE.md section 2.
"""
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "runtime_data", "arch-figure")
os.makedirs(OUT, exist_ok=True)

INK = "#20272D"; BLUE = "#397EAA"; BLUE_FILL = "#CEE9FC"; DARKBLUE = "#294D69"
GREEN = "#547548"; GREEN_FILL = "#D3E8C7"; GREEN_TINT = "#EDF5E6"
AMBER = "#C3A253"; AMBER_FILL = "#FFF4D4"; GRAY = "#697B89"
PANEL_BG = "#F7FAFD"; PANEL_LINE = "#D7E0E8"; ROSE = "#C76E79"; WHITE = "#FFFFFF"
FONT = "Microsoft YaHei"

objs = []
def rect(id, x, y, w, h, fill, stroke, sw=1.6, radius=10, dashed=False, role="module"):
    o = {"id": id, "type": "rect", "role": role, "x": x, "y": y, "width": w, "height": h,
         "radius": radius, "fill": fill, "stroke": stroke, "strokeWidth": sw}
    if dashed: o["dashed"] = True
    objs.append(o); return o

def text(id, x, y, w, h, s, size=12, fill=INK, bold=False, align="left", halign=None):
    o = {"id": id, "type": "text", "role": "label", "x": x, "y": y, "width": w, "height": h,
         "text": s, "fontFamily": FONT, "fontSize": size, "fill": fill}
    if bold: o["bold"] = True
    if halign: o["align"] = halign
    objs.append(o); return o

def poly(id, pts, color=INK, sw=1.6, dashed=False, arrow=True, role="connector"):
    o = {"id": id, "type": "polyline", "role": role,
         "points": [[round(a, 1), round(b, 1)] for a, b in pts],
         "stroke": color, "strokeWidth": sw, "dashed": dashed, "endArrow": arrow}
    objs.append(o); return o

def badge(id, cx, cy, num, color=BLUE):
    rect(id + "-bg", cx - 13, cy - 13, 26, 26, color, color, sw=0, radius=13, role="badge")
    text(id + "-tx", cx - 13, cy - 9, 26, 20, str(num), size=14, fill="#FFFFFF", bold=True, halign="center")

# ---------- canvas ----------
W, H = 1560, 1000

text("title", 40, 26, 1480, 40, "Wellspring-Agent 四层架构：Kernel 不信任任何模型", size=27, fill=INK, bold=True)
text("subtitle", 40, 70, 1480, 26, "证据闭合科研运行时 · 结构出处 ARCHITECTURE.md §2 · 示意图，不是实验结果", size=13, fill=GRAY)

# ---------- panel (a) adapters ----------
rect("panel-a", 40, 104, 1000, 138, PANEL_BG, PANEL_LINE, sw=1.4, radius=12, dashed=True, role="panel")
text("panel-a-label", 56, 116, 700, 22, "(a) ADAPTERS 接入 · 人工门只在此层", size=12.5, fill=GRAY, bold=True)
adapters = [
    ("CLI", "claim / freeze / sign 在此执行"),
    ("MCP stdio", "41 工具 · 0 签核入口"),
    ("HTTP runtime", "127.0.0.1:8787 · SSE"),
    ("Python SDK", "client.py · 本地嵌入"),
]
for i, (t, s) in enumerate(adapters):
    x = 58 + i * 240
    rect("ad-%d" % i, x, 146, 226, 72, BLUE_FILL, BLUE, sw=1.8, radius=9)
    text("ad-%d-t" % i, x + 12, 158, 202, 22, t, size=13, fill=DARKBLUE, bold=True)
    text("ad-%d-s" % i, x + 12, 184, 202, 24, s, size=10, fill=INK)
badge("inn2", 1014, 128, 2)
text("inn2-label", 880, 120, 128, 20, "人工门在架构外", size=11, fill=ROSE, bold=True, halign="right")

# ---------- panel (b) skills ----------
rect("panel-b", 40, 286, 1000, 226, PANEL_BG, PANEL_LINE, sw=1.4, radius=12, dashed=True, role="panel")
text("panel-b-label", 56, 296, 340, 22, "(b) SKILLS 流程与策略 · S0→S16", size=12.5, fill=GRAY, bold=True)
stages = [
    ("S0", "问题框定", "task-agent", ""),
    ("S1", "检索与全文", "literature", "Q0"),
    ("S1b", "综合矩阵", "synthesis", ""),
    ("S2-S3", "创新评审", "idea · G1", "G1"),
    ("S4", "实验设计", "design_audit", "G2"),
    ("S5", "本地执行", "run · study", ""),
    ("S6", "图表", "figure · G3", ""),
    ("S8-S12", "写作与评审", "writing · paper", ""),
    ("S13-S16", "闭包与签核", "closure · G5", "G5"),
]
bw, bh, gap = 100, 96, 7
x0, y0 = 58, 348
for i, (sid, name, sub, gate) in enumerate(stages):
    x = x0 + i * (bw + gap)
    rect("sk-%d" % i, x, y0, bw, bh, BLUE_FILL, BLUE, sw=1.8, radius=9)
    text("sk-%d-id" % i, x + 10, y0 + 10, bw - 20, 18, sid, size=12, fill=DARKBLUE, bold=True)
    text("sk-%d-n" % i, x + 10, y0 + 34, bw - 16, 38, name, size=12, fill=INK, bold=True)
    text("sk-%d-s" % i, x + 10, y0 + 72, bw - 16, 18, sub, size=8.5, fill=GRAY)
    if i < len(stages) - 1:
        poly("edge-%d" % i, [(x + bw + 1, y0 + bh / 2), (x + bw + gap - 1, y0 + bh / 2)], color=INK, sw=1.6)
    if gate:
        gate_txt = ("门 %s" % gate) if gate == "Q0" else ("门 %s 人工" % gate)
        text("gate-%d" % i, x + 10, y0 + bh + 8, bw, 18, gate_txt, size=10.5, fill="#8A6D1F", bold=True)
# lineage loop (innovation 3): S13-S16 top -> up -> left -> down into S0 top
loop_y = 336
poly("lineage-loop", [(x0 + 8 * (bw + gap) + bw / 2, y0 - 4), (x0 + 8 * (bw + gap) + bw / 2, loop_y),
                      (x0 + bw / 2, loop_y), (x0 + bw / 2, y0 - 4)],
     color=ROSE, sw=1.6, dashed=True)
text("lineage-label", 410, 312, 620, 20,
     "③ lineage 失效回环：交付后变更沿依赖图传播 stale → 结论拉回重签", size=11, fill=ROSE, bold=True)
badge("inn3", 380, loop_y - 22, 3, color=ROSE)
badge("inn1", 920, y0 - 14, 1)
text("inn1-label", 936, y0 - 26, 106, 34, "① span-only 资格判定", size=10, fill=DARKBLUE, bold=True)

# ---------- panel (c) capabilities ----------
rect("panel-c", 40, 556, 1000, 122, PANEL_BG, PANEL_LINE, sw=1.4, radius=12, dashed=True, role="panel")
text("panel-c-label", 56, 568, 700, 22, "(c) CAPABILITIES 可插拔能力 · 换实现不换约束", size=12.5, fill=GRAY, bold=True)
caps = [
    "retriever · OpenAlex / local / fixture", "parser", "local runner · iris / breast_cancer / chemlab",
    "writer", "figure renderer · AstraDraw*", "citation verifier · GB/T 7714", "journal template",
]
for i, t in enumerate(caps):
    row, col = divmod(i, 4)
    x = 58 + col * 244; y = 594 + row * 38
    rect("cap-%d" % i, x, y, 232, 32, WHITE, PANEL_LINE, sw=1.4, radius=7, dashed=True, role="chip")
    text("cap-%d-t" % i, x + 10, y + 8, 214, 18, t, size=9.5, fill=INK)

# ---------- panel (d) kernel ----------
rect("panel-d", 40, 722, 1000, 150, GREEN_TINT, GREEN, sw=2.0, radius=12, role="panel")
text("panel-d-label", 56, 734, 900, 22, "(d) KERNEL 稳定内核 · 不允许绕过 · 目标：不信任任何模型或外部 Skill", size=12.5, fill=GREEN, bold=True)
kern = ["Span-only 证据", "Claim/EA/Gate/Signature 写权限", "human gates Q0·G1·G2·S5b·G5",
        "artifact hash · RunCapsule · allowlist", "路径越界校验", "审计"]
for i, t in enumerate(kern):
    row, col = divmod(i, 3)
    x = 58 + col * 322; y = 766 + row * 44
    rect("k-%d" % i, x, y, 306, 36, GREEN_FILL, GREEN, sw=1.4, radius=7, role="chip")
    text("k-%d-t" % i, x + 10, y + 9, 288, 20, t, size=10.5, fill="#1F3D2C", bold=True)

# ---------- buses between panels ----------
for i in range(4):
    x = 58 + i * 240 + 113
    poly("bus-a%d" % i, [(x, 242), (x, 264)], color=INK, sw=1.6, arrow=False)
poly("bus-a-line", [(171, 264), (964, 264)], color=INK, sw=1.6, arrow=False)
for i in range(9):
    x = x0 + i * (bw + gap) + bw / 2
    poly("bus-b%d" % i, [(x, 264), (x, 282)], color=INK, sw=1.6)
for i in range(4):
    x = 174 + i * 244
    poly("bus-bc%d" % i, [(x, 512), (x, 534)], color=INK, sw=1.6, arrow=False)
poly("bus-bc-line", [(174, 534), (906, 534)], color=INK, sw=1.6, arrow=False)
for i in range(4):
    x = 174 + i * 244
    poly("bus-c%d" % i, [(x, 534), (x, 590)], color=INK, sw=1.6)
poly("bus-cd", [(793, 678), (793, 718)], color=INK, sw=1.8)

# ---------- governance rail ----------
rect("panel-g", 1080, 104, 440, 570, "#FDFAF3", AMBER, sw=1.6, radius=12, dashed=True, role="panel")
text("panel-g-label", 1096, 116, 400, 22, "(e) GOVERNANCE 治理面 META · 垂直贯穿", size=12.5, fill="#8A6D1F", bold=True)
gov = [
    ("RSI 租约门控自改进", "propose → dry-run → 四套评测 → 人签 → TTL 租约 → 消费复查"),
    ("autopilot 委托", "人写一次策略 · 每步带策略 SHA-256 · 越界即停"),
    ("host-model · waitpoints", "宿主只供草稿 · S4 设计挂起等人作答"),
    ("skills registry", "外部技能蒸馏候选 · 默认 disabled"),
    ("guideline-memory · mandate", "经验块准入 · 委托状态"),
]
for i, (t, s) in enumerate(gov):
    y = 148 + i * 102
    rect("gov-%d" % i, 1096, y, 408, 88, AMBER_FILL, AMBER, sw=1.6, radius=9)
    text("gov-%d-t" % i, 1110, y + 12, 380, 22, t, size=12.5, fill="#5C4A14", bold=True)
    text("gov-%d-s" % i, 1110, y + 40, 380, 40, s, size=10, fill=INK)
badge("inn4", 1096, 148 + 44, 4, color=AMBER)
# dashed taps governance -> skills
for i in range(3):
    y = 200 + i * 150
    poly("tap-%d" % i, [(1078, y), (1044, y)], color=AMBER, sw=1.5, dashed=True, arrow=False)

# ---------- legend ----------
rect("legend", 1080, 692, 440, 258, WHITE, PANEL_LINE, sw=1.4, radius=12, role="panel")
text("legend-title", 1096, 704, 300, 22, "图例 · 创新点索引", size=12.5, fill=INK, bold=True)
legend = [
    (BLUE_FILL, BLUE, "流程与策略（可插拔）"),
    (GREEN_FILL, GREEN, "固定内核：验证与写权限"),
    (AMBER_FILL, AMBER, "治理面 META（垂直贯穿）"),
]
for i, (f, s, t) in enumerate(legend):
    y = 736 + i * 30
    rect("lg-%d" % i, 1096, y, 26, 18, f, s, sw=1.4, radius=5)
    text("lg-%d-t" % i, 1132, y + 2, 370, 18, t, size=10.5, fill=INK)
poly("lg-solid", [(1096, 832), (1124, 832)], color=INK, sw=1.6)
text("lg-solid-t", 1132, 824, 370, 18, "实线箭头：调用与数据流", size=10.5, fill=INK)
poly("lg-dash", [(1096, 860), (1124, 860)], color=ROSE, sw=1.6, dashed=True)
text("lg-dash-t", 1132, 852, 370, 18, "虚线：治理 / 反馈 / 失效回环", size=10.5, fill=INK)
text("lg-inn", 1096, 884, 410, 58,
     "创新点：① span-only 证据资格  ② 人工门在架构外  ③ lineage 失效回环  ④ 租约门控自改进",
     size=10.5, fill=DARKBLUE, bold=True)

# ---------- footer ----------
text("footer", 40, 962, 1480, 24,
     "human gates（Q0 / G1 / G2 / S5b / G5）的唯一入口是本地 CLI；签署之前“文章”只是骨架。* AstraDraw 为 vendored 第三方，发行包不含。",
     size=11, fill=GRAY)

scene = {
    "schema_version": 1,
    "id": "wellspring-architecture-figure",
    "component": "research-agent-four-layer-architecture",
    "style": "paper-method",
    "width": W,
    "height": H,
    "scientific_notes": [
        "Schematic architecture diagram; not an experimental result and not a data plot.",
        "Layer structure, stage ids, gates and module names come from ARCHITECTURE.md §2 and loop_ledger.py.",
        "Innovation callouts 1-4 map to span-only evidence, architecture-external human gates, lineage stale loop, lease-gated RSI.",
    ],
    "objects": objs,
}

out = os.path.join(OUT, "architecture.scene.json")
with io.open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(scene, f, ensure_ascii=False, indent=1)
print("scene written:", out, "| objects:", len(objs))
