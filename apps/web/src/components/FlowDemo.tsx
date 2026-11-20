import { useState } from "react";
import { useWorkspaceStore } from "../state/workspaceStore";

/**
 * Front-end walkthrough of the whole research flow, S1 survey -> META.
 *
 * This is a DEMO state machine: everything is local React state, nothing is
 * written to disk, and no signature.json is produced. The "模拟人签" button
 * only replays what a completed chain *looks like*; the real signature is
 * still created by the local CLI. Keeping it in memory (reset on refresh) is
 * deliberate so a demo can never be mistaken for a signed result.
 */

type Stage = {
  id: string;
  label: string;
  cmd: string;
  artifact: string;
  detail: string;
  gate?: string;
  human?: boolean;
  obligation: string;
};

const STAGES: Stage[] = [
  {
    id: "S1",
    label: "文献检索",
    cmd: "retrieval.query",
    artifact: "4 sources · 12 spans · 2 gaps",
    detail: "把问题拆成可检索的子问题，先写清楚「什么算证据」。摘要-only 只作 SourceHit，不生成 span；有全文才有可定位片段。",
    obligation: "可定位的 span 就位"
  },
  {
    id: "S2–S3",
    label: "假设收敛",
    cmd: "idea.frame",
    artifact: "2 candidates · H1 / H2",
    detail: "从 coverage gap 生成候选假设。候选不是 claim；必须经 G1 人工收敛后才能进入设计。",
    gate: "G1",
    human: true,
    obligation: "人选定主假设与竞争假设"
  },
  {
    id: "S4",
    label: "设计冻结",
    cmd: "design.freeze",
    artifact: "预注册协议 · 哈希绑定",
    detail: "协议先于数据：假设、基线、主指标、seeds、对照组在此定死。执行器之后只做提取与统计，无权改协议。",
    gate: "G2",
    human: true,
    obligation: "人确认并冻结协议"
  },
  {
    id: "S5a",
    label: "复现执行",
    cmd: "run.work",
    artifact: "RUN-014 · 3 seeds · R² 0.164 vs −0.048",
    detail: "数据、代码版本、协议哈希与种子写入 RunCapsule；EA 用 sha256 钉住结果文件，任何改动都会被发现。",
    obligation: "RunCapsule completed · EA immutable"
  },
  {
    id: "S5b",
    label: "证据判定",
    cmd: "judge.verify",
    artifact: "EA sealed · verdict",
    detail: "两态 verdict 加 underpowered 守卫：区间跨零、样本不足时标注「too few to interpret a sign」，不把「没测出差异」写成「无效」。负结果如实保留。",
    gate: "待人签",
    human: true,
    obligation: "statement + human_reason 由人定稿"
  },
  {
    id: "S6",
    label: "结果图",
    cmd: "figure.render",
    artifact: "SVG + manifest · bound to EA",
    detail: "图绑定 EA；上游数据变更后，受影响的图被标记 stale 并暂停导出，不会拿旧图配新结论。",
    obligation: "图与 EA 一致"
  },
  {
    id: "S8–S12",
    label: "写作槽位",
    cmd: "paper.bind",
    artifact: "results / figure / abstract",
    detail: "槽位只接受已签 claim / EA / closure 引用；正文不会先于证据填数。Limitations 必须由作者写，不能由 agent 代填。",
    obligation: "正文绑定已签证据"
  },
  {
    id: "S13–S16",
    label: "闭包检查",
    cmd: "closure.check",
    artifact: "lineage verify · export manifest",
    detail: "核对 claim / EA / 签名 / 沿袭四件产物一致性；不一致即 blocked。签名只在本地 CLI 产生，网页不代签。",
    gate: "G5",
    human: true,
    obligation: "人签 claim → closure → signature"
  },
  {
    id: "META",
    label: "自改进提案",
    cmd: "rsi.propose",
    artifact: "candidate · lease 未授予",
    detail: "把有效经验写成方法插件补丁，不训练模型权重。lease 授予前不生效；采纳由人决定。版本迭代不改骨架、单题参数不上长、新版不追认旧结果。",
    obligation: "人授予 lease 后经验才可复用"
  }
];

const SIGN_STEP = 5; // S5b (index 4) must be reached before the demo signing button appears

const CHAIN = [
  { label: "来源", sub: "SOURCE", need: 1 },
  { label: "片段", sub: "SPAN", need: 1 },
  { label: "运行记录", sub: "CAPSULE", need: 4 },
  { label: "证据制品", sub: "EA", need: 4 },
  { label: "断言", sub: "CLAIM", need: 8 }
];

const SLOTS = [
  { id: "S8.methods", label: "Methods", need: 3 },
  { id: "S9.results", label: "Results", need: 8 },
  { id: "S10.figure", label: "Figure", need: 8 },
  { id: "S11.abstract", label: "Abstract", need: 8 },
  { id: "S12.related", label: "Related", need: 9 },
  { id: "S12.limitations", label: "Limitations", need: 99 }
];

export function FlowDemo() {
  const [step, setStep] = useState(0);
  const [signed, setSigned] = useState(false);
  const [open, setOpen] = useState<number | null>(0);
  const setUI = useWorkspaceStore((state) => state.actions.setUI);
  const notify = useWorkspaceStore((state) => state.actions.notify);
  const currentMessages = useWorkspaceStore(
    (state) => state.tasks.find((t) => t.id === state.selectedTaskId)?.messages ?? []
  );

  // Clicking a flow node expands its detail AND jumps the conversation thread
  // to the first message tagged with that stage, so a presenter can point at a
  // stage and see the corresponding evidence/action in the transcript.
  const focusInThread = (stageId: string) => {
    const hasStage = currentMessages.some((m) => m.stage === stageId);
    if (!hasStage) {
      notify(`当前会话没有「${stageId}」的定位消息；切到「完整闭环」会话可体验阶段↔会话联动`);
      return;
    }
    setUI({ focusStage: { id: stageId, tick: Date.now() } });
  };

  const signDemo = () => {
    if (step < SIGN_STEP || signed) return;
    setSigned(true);
    setStep(8); // writing + closure done in the replay
    setOpen(7);
  };

  const reset = () => {
    setStep(0);
    setSigned(false);
    setOpen(0);
  };

  const done = (i: number) => i < step || (signed && i <= 7);
  const canAdvance = step < STAGES.length;
  const effectiveStep = signed ? 8 : step;

  return (
    <div className="context-stack flow-demo">
      <div className="flow-banner">
        <div className="flow-banner-title">
          <span className="flow-dot" /> 全流程演示 · FRONT-END REPLAY
        </div>
        <p>
          从文献检索一路走到结论签署与自改进。这是<b>前端推演</b>：所有状态只在页面内存中，「模拟人签」不会生成真实
          signature.json；真实签名仍须在本地 CLI 执行。刷新页面即回到待签。
        </p>
        <p className="flow-banner-hint">
          和左侧会话的分工：<b>左侧是"已走完整场"的回放</b>（可以直接读每一轮结论）；<b>这里是从第 0 步亲手推一遍</b>的教学版——所以进度各自独立，按「推进下一步」走给你看即可。
          每步写的产物数字是<b>教学示例</b>，不是当前任务的真实读数；真实读数以左侧对话为准。
        </p>
      </div>

      <div className="flow-controls">
        <button
          type="button"
          className="flow-btn primary"
          disabled={!canAdvance}
          onClick={() => {
            if (!canAdvance) return;
            // Open the stage we just advanced *into* (index === old step), not
            // the one we completed. Using the stale `step` here used to expand
            // the previous stage, so the presenter could never point at the
            // current one.
            const next = step + 1;
            setStep(next);
            setOpen(Math.min(next, STAGES.length - 1));
          }}
        >
          推进下一步 →
        </button>
        <button
          type="button"
          className="flow-btn sign"
          disabled={step < SIGN_STEP || signed}
          title={step < SIGN_STEP ? "先推进到「证据判定」才能演示签署" : "演示人签完成后的状态"}
          onClick={signDemo}
        >
          {signed ? "✓ 已签（演示）" : "模拟人签 → 已签"}
        </button>
        <button type="button" className="flow-btn" onClick={reset}>
          重置为待签
        </button>
        <span className={`flow-state ${signed ? "is-signed" : ""}`} title="教学重演：从第 0 步开始，与左侧已录完的回放进度无关">
          {signed ? "已签 · DEMO" : `教学重演 · 待签 · 第 ${step}/${STAGES.length} 步`}
        </span>
      </div>

      <section className="context-card">
        <div className="card-label">
          <span>RESEARCH FLOW</span>
          <em>{signed ? "SIGNED · DEMO" : "REPLAY · 教学重演"}</em>
        </div>
        <ol className="flow-stages">
          {STAGES.map((stage, i) => (
            <li
              key={stage.id}
              className={`flow-stage ${done(i) ? "is-done" : ""} ${open === i ? "is-open" : ""} ${
                stage.human ? "is-human" : ""
              }`}
            >
              <button
                type="button"
                className="flow-stage-head"
                onClick={() => {
                  setOpen(open === i ? null : i);
                  focusInThread(stage.id);
                }}
                aria-expanded={open === i}
                title="展开详情，并定位到历史会话中该阶段对应的消息"
              >
                <span className="flow-stage-mark">{done(i) ? "✓" : stage.human ? "人" : "·"}</span>
                <span className="flow-stage-id">{stage.id}</span>
                <span className="flow-stage-label">{stage.label}</span>
                {/* One gate marker only. The "人" mark above and this gate badge
                    already say "human gate"; a third amber "人工" chip used to
                    duplicate both and introduce a second colour for one idea. */}
                {stage.gate ? <span className="flow-stage-gate">{stage.gate}</span> : null}
                <span
                  className="flow-stage-jump"
                  role="button"
                  tabIndex={0}
                  title="跳到会话中对应消息"
                  aria-label={`跳到会话中 ${stage.id} ${stage.label} 对应的消息`}
                  onClick={(event) => {
                    event.stopPropagation();
                    focusInThread(stage.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      event.stopPropagation();
                      focusInThread(stage.id);
                    }
                  }}
                >
                  ↗
                </span>
              </button>
              {open === i ? (
                <div className="flow-stage-body">
                  <div className="flow-kv">
                    <span>命令</span>
                    <code>{stage.cmd}</code>
                  </div>
                  <div className="flow-kv">
                    <span>产物（示例）</span>
                    <code>{stage.artifact}</code>
                  </div>
                  <p>{stage.detail}</p>
                  <div className="flow-obligation">
                    <span>下一步义务</span>
                    <b>{stage.obligation}</b>
                  </div>
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      <section className="context-card">
        <div className="card-label">
          <span>EVIDENCE CHAIN</span>
          <em>{signed ? "5/5 · DEMO SIGNED" : "4/5 · 断言待人工"}</em>
        </div>
        <div className="flow-chain">
          {CHAIN.map((node, i) => {
            const lit = effectiveStep >= node.need;
            const isClaim = i === CHAIN.length - 1;
            return (
              <div
                className={`flow-chain-node ${lit ? "is-lit" : ""} ${isClaim && !signed ? "is-wait" : ""}`}
                key={node.sub}
                title={isClaim && !signed ? "断言需人工签署；演示中由「模拟人签」点亮" : undefined}
              >
                <span>{node.label}</span>
                <b>{node.sub}</b>
                <i>{lit ? (isClaim && !signed ? "待人工" : "✓") : "·"}</i>
              </div>
            );
          })}
        </div>
        <p className="flow-note">
          {signed
            ? "演示推演：五段全绿只表示「签好后长这样」。真实签名由本地 CLI 产生并写入产物，页面不代签。"
            : "待签 = 证据齐了，但 statement 与 human_reason 还没由人定稿；签名只在本地 CLI 完成。"}
        </p>
      </section>

      <section className="context-card">
        <div className="card-label">
          <span>WRITING SLOTS</span>
          <em>{signed ? "BOUND · DEMO" : "LOCKED"}</em>
        </div>
        <div className="flow-slots">
          {SLOTS.map((slot) => {
            const bound = signed && slot.need <= 8;
            const special = slot.id === "S12.limitations";
            return (
              <div
                className={`flow-slot ${special ? "is-author" : bound ? "is-bound" : "is-locked"}`}
                key={slot.id}
              >
                <span>{slot.label}</span>
                <b>{special ? "作者写" : bound ? "bound" : "locked"}</b>
              </div>
            );
          })}
        </div>
        <p className="flow-note">
          正文不先于证据填数：Results / Figure / Abstract 绑定已签 claim 与 EA；Limitations 始终由作者撰写。
        </p>
      </section>

      <div className="flow-boundary">
        <b>边界：</b>本演示不调用模型、不执行实验、不写盘、不生成真实签名。它只用于说明「待签」与「已签」各是什么状态、以及完整流程如何闭合。
      </div>
    </div>
  );
}
