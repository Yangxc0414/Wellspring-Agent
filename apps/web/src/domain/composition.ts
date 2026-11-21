/**
 * Element ports + compositions (design/154).
 *
 * Self-correction against the seminar transcript: design/151 still presented
 * ONE linear element chain, which quietly re-encoded the order into the
 * meta-model. The advisor explicitly rejected that: the meta-model is ELEMENTS
 * WITH PORTS (what each consumes/produces); a research method is a COMPOSITION
 * (a wiring); different wirings are different valid orders, and swapping two
 * elements changes what flows between ports.
 *
 * Two reference compositions are modeled here (both standard empirical-
 * methodology shapes, Easterbrook et al. 2008 / Creswell 2014):
 *  - CONFIRMATORY (验证式): hypothesis is formed BEFORE the design; the design
 *    consumes the hypothesis to become a discriminating protocol.
 *  - EXPLORATORY (探索式): the data-collection design comes FIRST (it cannot
 *    consume a hypothesis that does not exist yet); hypotheses are distilled
 *    FROM the evidence afterwards.
 * The governance gates (判签/闭包/经验) and their semantics are identical in
 * both — that is the 不变 layer. Everything here is display-level derivation
 * of the same SPEC invariants elementGraph.ts carries; no gate semantics change.
 */

export type PortType =
  | "研究问题"
  | "候选假设（可判别）"
  | "提炼式假设（事后）"
  | "探索式数据收集设计"
  | "判别式协议"
  | "数据收集协议"
  | "RunCapsule + EA"
  | "ClaimRecord"
  | "图 manifest"
  | "稿件绑定"
  | "closure + 导出"
  | "任务反馈";

export interface ElementPorts {
  id: string;
  label: string;
  /** 该要素可消费的输入端口类型（一种要素可以有多个可选输入端口）。 */
  inputKinds: PortType[];
  /** 产出规则：消费哪个输入端口，就产出对应的输出端口。方案的输出随
   * 输入变化（消费假设→判别式协议；消费问题→数据收集协议）——这正是
   * 「顺序调换改变输入输出关系」的结构化表达。 */
  outputs: Array<{ consumes: PortType | null; produces: PortType }>;
  human: boolean;
}

export const PORT_ELEMENTS: ElementPorts[] = [
  { id: "问题", label: "研究问题", inputKinds: [], outputs: [{ consumes: null, produces: "研究问题" }], human: false },
  {
    id: "假设",
    label: "问题与假设",
    // 验证式：假设消费研究问题（先验）；探索式：假设消费证据（事后提炼，
    // 扎根式）——同一个要素，两种接线，产出端口随之不同。
    inputKinds: ["研究问题", "RunCapsule + EA"],
    outputs: [
      { consumes: "研究问题", produces: "候选假设（可判别）" },
      { consumes: "RunCapsule + EA", produces: "提炼式假设（事后）" }
    ],
    human: true
  },
  {
    id: "方案",
    label: "研究方案（设计冻结）",
    inputKinds: ["候选假设（可判别）", "研究问题"],
    outputs: [
      { consumes: "候选假设（可判别）", produces: "判别式协议" },
      { consumes: "研究问题", produces: "数据收集协议" }
    ],
    human: true
  },
  {
    id: "证据",
    label: "证据生产（执行）",
    inputKinds: ["判别式协议", "数据收集协议"],
    outputs: [
      { consumes: "判别式协议", produces: "RunCapsule + EA" },
      { consumes: "数据收集协议", produces: "RunCapsule + EA" }
    ],
    human: false
  },
  {
    id: "判定",
    label: "断言与签核",
    inputKinds: ["RunCapsule + EA"],
    outputs: [{ consumes: "RunCapsule + EA", produces: "ClaimRecord" }],
    human: true
  },
  {
    id: "图表",
    label: "结果图表",
    inputKinds: ["RunCapsule + EA"],
    outputs: [{ consumes: "RunCapsule + EA", produces: "图 manifest" }],
    human: false
  },
  {
    id: "写作",
    label: "写作与评审",
    inputKinds: ["ClaimRecord", "图 manifest"],
    outputs: [{ consumes: "ClaimRecord", produces: "稿件绑定" }],
    human: true
  },
  {
    id: "闭包",
    label: "闭包与导出签核",
    inputKinds: ["ClaimRecord", "RunCapsule + EA"],
    outputs: [{ consumes: "ClaimRecord", produces: "closure + 导出" }],
    human: true
  },
  {
    id: "经验",
    label: "经验与自改进",
    inputKinds: ["closure + 导出"],
    outputs: [{ consumes: "closure + 导出", produces: "任务反馈" }],
    human: true
  }
];

/** A wiring step: which element runs, consuming which input port. */
export interface WiringStep {
  element: string;
  /** The input port this step actually consumes (null = entry element). */
  consumes: PortType | null;
  /** design/166: why this element sits at this position. Present on the
   *  registry copy; the built-in fallback wirings omit it. */
  rationale?: string;
}

export interface Composition {
  id: "confirmatory" | "exploratory";
  label: string;
  sub: string;
  /** The claim gate pause still applies (governance is identical). */
  wiring: WiringStep[];
}

export const COMPOSITIONS: Record<"confirmatory" | "exploratory", Composition> = {
  confirmatory: {
    id: "confirmatory",
    label: "验证式组合",
    sub: "假设在前：方案消费假设，成为判别式协议",
    wiring: [
      { element: "问题", consumes: null },
      { element: "假设", consumes: "研究问题" },
      { element: "方案", consumes: "候选假设（可判别）" },
      { element: "证据", consumes: "判别式协议" },
      { element: "判定", consumes: "RunCapsule + EA" },
      { element: "图表", consumes: "RunCapsule + EA" },
      { element: "写作", consumes: "ClaimRecord" },
      { element: "闭包", consumes: "ClaimRecord" },
      { element: "经验", consumes: "closure + 导出" }
    ]
  },
  exploratory: {
    id: "exploratory",
    label: "探索式组合",
    sub: "证据在前：方案只消费问题（数据收集设计），假设从证据中提炼",
    wiring: [
      { element: "问题", consumes: null },
      { element: "方案", consumes: "研究问题" },
      { element: "证据", consumes: "数据收集协议" },
      { element: "假设", consumes: "RunCapsule + EA" },
      { element: "判定", consumes: "RunCapsule + EA" },
      { element: "写作", consumes: "ClaimRecord" },
      { element: "闭包", consumes: "ClaimRecord" },
      { element: "经验", consumes: "closure + 导出" }
    ]
  }
};

export const COMPOSITION_ORDER: Array<"confirmatory" | "exploratory"> = [
  "confirmatory",
  "exploratory"
];

export interface WiringViolation {
  step: number;
  element: string;
  message: string;
}

/**
 * Port-matching validation: a wiring is legal iff every step's consumed port
 * is satisfied by (a) the entry (research question) or (b) an output port of
 * an EARLIER step, and the element actually declares that input kind. This is
 * how "顺序由依赖推导" becomes executable: illegal wirings are checkable.
 */
export function validateComposition(composition: Composition): WiringViolation[] {
  const violations: WiringViolation[] = [];
  const available: PortType[] = ["研究问题"];
  const elements = new Map(PORT_ELEMENTS.map((item) => [item.id, item]));
  composition.wiring.forEach((step, index) => {
    const element = elements.get(step.element);
    if (!element) {
      violations.push({ step: index, element: step.element, message: "未知要素" });
      return;
    }
    let produced: PortType | null = null;
    if (step.consumes) {
      if (!element.inputKinds.includes(step.consumes)) {
        violations.push({
          step: index,
          element: step.element,
          message: `${step.element} 不消费端口「${step.consumes}」`
        });
      }
      if (!available.includes(step.consumes)) {
        violations.push({
          step: index,
          element: step.element,
          message: `上游尚未产出端口「${step.consumes}」`
        });
      }
      // The output port follows the consumed input port (方案's output differs
      // by mode: consuming the hypothesis yields a discriminating protocol,
      // consuming the question yields a data-collection protocol).
      const rule = element.outputs.find(
        (item) => item.consumes === step.consumes || item.consumes === null
      );
      produced = rule?.produces ?? null;
    } else {
      const rule = element.outputs.find((item) => item.consumes === null);
      produced = rule?.produces ?? null;
    }
    if (produced) available.push(produced);
  });
  return violations;
}
