/**
 * Human-gate CLI commands shown by the UI.
 *
 * The browser never performs Q0/G1/G2/S5b/G5 human acts: claim signature, protocol
 * freeze, experiment approval, closure/export signature only exist as local CLI
 * commands (AGENTS.md §7: no approve/sign/freeze/publish endpoint or MCP tool).
 * Every form below mirrors `research_agent/cli.py`; ids the component does not own
 * stay explicit placeholders instead of invented values.
 */

export const CLI_ONLY_NOTE = "签名与冻结只留在本地 CLI：网页不代签、不写证据层，点击这里只是显示命令。";

export interface GateCommandInput {
  projectDir?: string;
  runDir?: string;
  experimentId?: string;
  reportFile?: string;
  claimFile?: string;
  demoFile?: string;
  scope?: string;
}

function orPlaceholder(value: string | undefined, placeholder: string): string {
  const trimmed = (value ?? "").trim();
  return trimmed || placeholder;
}

/** G1 hypothesis convergence — `research_agent flow g1` writes g1-decision.json. */
export function g1DecisionCommand(input: GateCommandInput = {}, ideaId?: string, humanReason?: string): string {
  const dir = orPlaceholder(input.projectDir, "<output-dir>");
  const ideaFile = orPlaceholder(input.demoFile, `${dir}/idea.json`);
  const id = orPlaceholder(ideaId, "<IDEA-ID>");
  const reason = orPlaceholder(humanReason, "<为什么收敛到这个候选>");
  return [
    "python -m research_agent flow g1 \\",
    `  --idea-file ${ideaFile} \\`,
    `  --idea-id ${id} \\`,
    `  --human-reason "${reason}" \\`,
    `  --output-dir ${dir}`
  ].join("\n");
}

/** Q0/S5b claim signature — `research_agent run claim`. */
export function claimSignCommand(input: GateCommandInput = {}, humanReason?: string): string {
  const runDir = orPlaceholder(input.runDir, "<run-dir>");
  const reason = orPlaceholder(humanReason, "已核对 EA 与指标");
  const lines = [
    "python -m research_agent run claim \\",
    `  --capsule ${runDir}/run-capsule.json \\`,
    `  --ea ${runDir}/ea.json \\`,
    '  --statement "<claim-draft.json 中的 statement>" \\',
    `  --human-reason "${reason}" \\`
  ];
  if (input.scope) {
    lines.push(`  --scope "${orPlaceholder(input.scope, "<S5/scope>")}" \\`);
  }
  lines.push(`  --output-dir ${runDir}/claim`);
  return lines.join("\n");
}

/** G2 protocol freeze — `research_agent protocol freeze` (design must exist). */
export function protocolFreezeCommand(input: GateCommandInput = {}, humanReason?: string): string {
  const project = orPlaceholder(input.projectDir, "<project>");
  const runDir = orPlaceholder(input.runDir, "<run-dir>");
  const experimentId = orPlaceholder(input.experimentId, "<EXP-ID>");
  const reason = orPlaceholder(humanReason, "已核对 baseline / 主指标 / seeds");
  return [
    "python -m research_agent protocol freeze \\",
    `  --design ${project}/experiments/${experimentId}/experiment.json \\`,
    `  --capsule ${runDir}/run-capsule.json \\`,
    '  --limitation "本次适用范围与已知局限" \\',
    `  --human-reason "${reason}" \\`,
    `  --output-dir ${project}/protocol`
  ].join("\n");
}

/** S4 human approval + explicit local execution — `experiment approve` then `experiment run`. */
export function experimentApproveCommands(input: GateCommandInput = {}): string[] {
  const project = orPlaceholder(input.projectDir, "<project>");
  const experimentId = orPlaceholder(input.experimentId, "<EXP-ID>");
  return [
    `python -m research_agent experiment approve \\\n  --project ${project} \\\n  --experiment-id ${experimentId} \\\n  --human-reason "已核对设计 / 数据 / 切分"`,
    `python -m research_agent experiment run \\\n  --project ${project} \\\n  --experiment-id ${experimentId} \\\n  --allow-execute`
  ];
}

/** G5 closure + export signature — `research_agent closure sign`. */
export function closureSignCommand(input: GateCommandInput = {}, humanReason?: string): string {
  const project = orPlaceholder(input.projectDir, "<project>");
  const runDir = orPlaceholder(input.runDir, "<run-dir>");
  const report = orPlaceholder(input.reportFile, `${project}/closure/<CLOSURE-ID>/closure-report.json`);
  const demo = orPlaceholder(input.demoFile, `${project}/closure/<CLOSURE-ID>/demo.json`);
  const claim = orPlaceholder(input.claimFile, `${runDir}/claim/claim.json`);
  const reason = orPlaceholder(humanReason, "已复核 closure 与导出清单");
  return [
    "python -m research_agent closure sign \\",
    `  --report ${report} \\`,
    `  --demo ${demo} \\`,
    `  --claim ${claim} \\`,
    `  --human-reason "${reason}" \\`,
    `  --output-dir ${project}/closure-signature`
  ].join("\n");
}
