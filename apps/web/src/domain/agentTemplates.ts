export interface AgentPreset {
  name: string;
  role: string;
  purpose: string;
  checks: string[];
}

export interface AgentTemplate {
  id: string;
  title: string;
  description: string;
  agents: AgentPreset[];
}

export const AGENT_TEMPLATES: AgentTemplate[] = [
  {
    id: "standard-review",
    title: "标准审稿组",
    description: "覆盖、引用、假设与协议四条独立审稿线，适合作为默认配置。",
    agents: [
      {
        name: "覆盖与引用审稿人",
        role: "reviewer",
        purpose: "检查全文覆盖与候选引用是否落在合并 span 中，提醒摘要-only 与引用断链。",
        checks: ["coverage", "citation"]
      },
      {
        name: "假设收敛审阅",
        role: "reviewer",
        purpose: "检查候选的证据支持、跨来源与 lens 多样性，避免把弱证据候选提前收敛。",
        checks: ["hypothesis"]
      },
      {
        name: "协议与方法审阅",
        role: "methodologist",
        purpose: "在 S4 检查 baseline、主指标、对照与 seeds，提醒协议是否具备冻结条件。",
        checks: ["protocol"]
      }
    ]
  },
  {
    id: "evidence-closure",
    title: "证据审计组",
    description: "把 claim/EA 边界与 closure/export 边界拆成两个审计角色。",
    agents: [
      {
        name: "证据边界审计",
        role: "auditor",
        purpose: "检查 span→EA→claim 的边界，发现越级 claim 与缺失证据引用。",
        checks: ["evidence"]
      },
      {
        name: "闭包与导出审计",
        role: "auditor",
        purpose: "检查 closure 未决项与导出前置条件，避免未闭合结果被导出。",
        checks: ["closure"]
      }
    ]
  },
  {
    id: "figure-provenance",
    title: "图表 provenance 组",
    description: "专门检查图与 EA/manifest 的绑定，适合结果图较多的任务。",
    agents: [
      {
        name: "图表 provenance 审阅",
        role: "reviewer",
        purpose: "检查 SVG、manifest、数据与 EA 的哈希和引用是否一致，避免图脱离证据单独存在。",
        checks: ["figure", "evidence"]
      }
    ]
  },
  {
    id: "full-loop",
    title: "全流程审稿组",
    description: "覆盖 S1–S16 的五个只读角色；创建数量最多，适合答辩/审稿前检查。",
    agents: [
      {
        name: "全流程覆盖与引用",
        role: "reviewer",
        purpose: "从 S1 开始检查来源、全文、span 与引用对齐，作为全流程审稿的第一道门。",
        checks: ["coverage", "citation"]
      },
      {
        name: "全流程假设审阅",
        role: "reviewer",
        purpose: "检查候选假设的证据支持与否证条件，避免 G1 之前过早收敛。",
        checks: ["hypothesis"]
      },
      {
        name: "全流程协议审阅",
        role: "methodologist",
        purpose: "检查 S4 协议是否在 run 前冻结，并核对 baseline、指标、对照与 seeds。",
        checks: ["protocol"]
      },
      {
        name: "全流程证据与图",
        role: "auditor",
        purpose: "检查 EA/claim/图 provenance 的绑定关系，发现证据链断点。",
        checks: ["evidence", "figure"]
      },
      {
        name: "全流程闭包审阅",
        role: "auditor",
        purpose: "检查 closure 与 export manifest，确认未闭合/已 stale 的内容不会被导出。",
        checks: ["closure"]
      }
    ]
  }
];
