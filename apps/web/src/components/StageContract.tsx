import { STAGE_MODULE_CONTRACTS } from "../domain/gateContracts";

/**
 * 一个阶段背后的后端契约（模块 + 硬约束）。数据来自 gateContracts
 * （转写自 AGENTS.md §5 与各 modules SPEC），所以面板展示的是系统真正怎么
 * 卡住这一步，而不只是 demo 怎么演。未知阶段渲染空——不编造契约。
 */
export function StageContract({ stageId }: { stageId: string }) {
  const mc = STAGE_MODULE_CONTRACTS[stageId];
  if (!mc) return null;
  return (
    <div className="flow-module-contract">
      <span>后端契约 · {mc.module}</span>
      <ul>
        {mc.invariants.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}
