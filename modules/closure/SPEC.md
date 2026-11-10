---
id: closure
name: 闭合与导出
stage: S13–S16
version: 0.18.1
status: draft
owner: research-agent
inputs:
  - PaperContract
  - ClaimRecord
  - RunCapsule
  - EvidenceArtifact
  - SupportPanel
outputs:
  - ClosureReport
  - Signature
  - ExportManifest
  - EvidenceBundle
  - BundleVerification
  - PipelineStaticAudit
tools:
  - closure.check
  - closure.sign
  - closure.publish
  - closure.profiles
  - closure.verify-bundle
  - closure.audit
gates:
  - G5
invariants:
  - 没有 Claim/EA 不能闭合
  - 结果槽未绑定不能导出
  - 未签署不能导出
  - 不自动投稿、不生成评审意见
  - 证据 bundle 不可覆盖；先 staging、逐文件哈希、fsync，再原子 rename
  - bundle 只接受 submission=false 的 export manifest，并重新校验全部字节
  - protocol/bibliography/result-figure 的伴随文件必须存在，且 id、状态、哈希与 demo 一致
  - closure report 必须把全部可定位的伴随证据写入 artifact_refs，不能只签 demo/claim/EA/capsule
  - 未决 obligation 不得因“后续报告不再列出”而自动 resolved；只能标 `unverified_disappearance`，并阻断 summary
  - obligation 只能通过人工显式 `resolve`（人理由 + 证据文件 SHA-256）或 `waive`（人理由）关闭；历史只追加
  - 若存在 support-panel.json，其 status 必须为 ready 或 not_applicable；needs_human/blocked/partial 或不可读一律阻断 closure
  - 有 signer 时必须记录 signer_id/key_id/scheme/signed_payload_sha256/HMAC；publish 必须重算并验证
  - 本地 HMAC 只证明持有本地 signer secret，不是 PKI、法律身份或同行评审
  - 第三套 profile search_study 与前两套词汇不互换、必须人签、submission_ready 恒 false
  - 盘点的链完整性只报告不判定：`integrity.state = non_derivable` 既不新增 blocker 也不解除任何 blocker，门禁仍由 `study closure` 决定；覆盖率数字必须同时给出 all 与 derivable 两个分母，不得混成一个
---

# 闭合与导出（S13–S16）

## Purpose

在论文契约、claim、run capsule 与 EA 之间做最终的闭合检查；只有所有结果槽绑定、EA 哈希一致、并且人工签署后，才允许生成导出 manifest。它不生成正文、不自动投稿。

## Contract

- 输入：pipeline `demo.json`（含 paper slots / run 模块）、`claim.json`；
- 检查：claim 必须 supported 且有 EA；EA 文件 sha256 必须与记录一致；RunCapsule 必须 completed；paper.result.primary 必须 `bound_claim` 且 claims 含 claim id；所有槽位必须非 pending；
- 检查伴随证据：bibliography 的 `entries` 重算哈希必须等于 `card_sha256`，bibliography 文件必须存在且 card id/状态/entry_count/hash 与 demo 一致；protocol 文件必须存在且 protocol id/status/capsule_sha256/human_reason 与 demo 一致；result-figure manifest 文件必须存在且内容与 demo 中的 manifest 一致，SVG 必须与 `svg_sha256` 一致；若存在 support-panel.json，其 status 必须为 ready/not_applicable，未裁决分歧直接 blocked；
- 输出：`ClosureReport`（checks、unresolved、status=blocked/ready、artifact_refs）；
- 失败：任何检查失败或存在 pending 槽位 → `blocked`，列出未决项；
- `closure sign` 只接受 `ready` 报告 + 非空人签理由；签署前会从当前 demo/claim 重新运行检查，提交报告 checks 必须与当前输入一致；export manifest 记录 closure checks 哈希与全部可定位输入文件哈希；不自动投稿。
- `closure publish` 读取一份 `submission=false` 的 export manifest，把 manifest 列出的证据文件、export manifest 自身和可选 signature 复制到新的不可变 bundle；逐文件重建 sha256、写 `bundle-manifest.json`，在 staging 完成 fsync 后原子 rename；目标已存在即失败，绝不覆盖。
- `closure verify-bundle` 只读重算 bundle 中每个文件的大小与 sha256，返回 `clean/stale`；缺失、篡改或 manifest 自身不一致均为 `stale`。
- `closure audit` 只做静态结构审计：检查核心产物存在、S1 span 能回到全文 hit、候选/设计引用能回到 span、G2 声称通过时必须有 frozen protocol、S5 capsule/EA 同 run_id、claim draft 未签且引用 EA、paper claim 槽位一致、schematic 图不得绑定为结果图、G5 声称通过必须有 closure；输出 `structurally_consistent_but_not_closed` / `structural_failure`，不重跑实验、不验证引用内容、不代替人签。
- 只读盘点（`closure profiles` / `/api/project-closures`，schema `closure-profiles-0.4`）：`canonical_run` 每行给出 profile/run_id/status/has_ea/has_claim_draft/has_signed_claim/closure_status/support_panel_status/next，未签署时另带 `claim_draft`（status、statement、scope、assertion、reading、command、cwd、boundary）；`command` 为相对项目根的 `run claim` 命令，statement/human-reason 保持占位符；签署后 `claim_draft=null`。它只展示下一步，不签、不改、不判真伪。
- `closure obligations` 维护 append-only 义务台账：`reconcile` 只新增/更新/标记复发；若未决项从新报告消失，状态变为 `unverified_disappearance`，不得自动 resolved。只有 `closure obligations resolve --id ... --reason ... --evidence <file>` 或 `waive --id ... --reason ...` 能关闭；`resolve` 记录证据文件 SHA-256，`waive` 明确标注人工豁免。`open/reopened/unverified_disappearance` 都使 summary 为 `blocked`。
- 盘点把"能不能验证"放到每一行研究旁边（schema `closure-profiles-0.7`）：`search_study` 行新增只读 `integrity`（`state = derivable | non_derivable | incomplete`、`failures`、`missing`、`code_fingerprint = match | stale | absent`），来自 `study_integrity.package_integrity`——即"包内记录的哈希能否由盘上字节在当前哈希规则下重推"，与"跑它的那版代码是否还在"分属两根轴。盘点顶层新增 `study_integrity_layers`（本次窗口内的包），`replication.chain_layers` 透传全库存扫描的分层覆盖表（每个披露 artifact 各有 `all` 与 `derivable` 两个分母，见 search-study 0.54.0）。这一行不重跑、不改判定：`non_derivable` 不新增 blocker，也不解除任何既有 blocker，它只是让读者看见覆盖率里有多少包无法再验证。

## Current Implementation

- `research_agent/closure.py`：`ClosureAgent.check` / `sign` / `publish` / `verify_bundle`；`audit_pipeline_bundle` 静态审计 pipeline 产物；`check` 读取真实 capsule 文件，并重算 claim.assertions；
- 检查 claim/EA 哈希、RunCapsule completed、paper.result.primary bound、result.figure provenance、bibliography_verified（DataCite 快照/2+ 条/哈希）、protocol_frozen；
- 预注册 ProtocolCard 可以 `capsule_sha256=""`，此时 `protocol_frozen` 接受 `protocol-binding` 中匹配 protocol_id/design_sha256/capsule_sha256 的绑定；artifact 路径统一 resolve，保证 sign 重校验稳定；
- `research_agent/signers.py` 提供本地 signer store 与 HMAC-SHA256；`closure sign --signer` 把 export manifest bytes、report_id、human_reason、submission=false 绑定为签名 payload；`closure publish` 在有 HMAC 签名时重新计算并验证，失败拒绝封装；`closure verify-bundle` 同时重算文件哈希与 sealed signature HMAC，输出 `signature_verified`；legacy-unsigned 只给 warning；
- ChemLab 绑定 claim + 数据图 + ProtocolCard + 4 条 DataCite 元数据后 11/11 检查 pass、status=ready；人签生成 submission=false 的 export manifest；
- 只读检查 demo/claim/EA/capsule/figure/protocol/bibliography，不修改它们；不联网；
- 签署前重新执行 check，旧报告不能绕过输入变化；export-manifest 增加 `closure_checks_sha256`、`revalidated_report_id`、`revalidated_at`；
- `publish`/`verify_bundle` 生成和校验自包含证据 bundle：`bundle-manifest.json` 记录源 export manifest、signature、每个源文件与 bundle 内相对路径、字节数与 sha256；bundle 内文件按其源文件字节逐一校验后复制，大小与哈希同时记录；
- `check` 会从 demo/claim 附近的规范位置解析 protocol、bibliography、result-figure manifest/SVG，并把它们写入 `artifact_refs`；缺少伴随文件会使 report blocked，而不是只签一个“demo 里写着有证据”的 JSON。
- `research_agent/obligations.py` 的 `reconcile` 不再把消失的未决项自动 resolved：状态改为 `unverified_disappearance`，summary 保持 blocked；新增 `resolve`/`waive` 显式人操作，`resolve` 要求证据文件存在并记录 SHA-256，`waive` 记录人工豁免理由；`closure obligations list/resolve/waive` 只走 CLI，不进 MCP/runtime。


## Boundaries

- 不判断科学正确性，不做同行评审；
- 不替代 G5 人工签署；
- 不把 blocked 报告写成“可投稿”；
- 不自动提交到期刊/基金系统。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `research_agent/closure.py` 与 `tests/test_closure.py`；
4. 跑 `python -m unittest discover -s tests -v`。

## Changelog
- 2026-11-11 · v0.18.1 · status=draft · 为 verdict-ledger 暴露只读别名 `claim_candidates(root, run)`：判定总线需要把 claim 判定行绑定到本模块实际读取的同一份 claim 文件，候选清单必须只有一处定义；`_claim_candidates` 行为一字未动，盘点输出不变。调用方 tests/test_verdict_ledger 钉绑定行为。最小改进，升 patch。
- 2026-11-02 · v0.18.0 · status=draft · 盘点每行研究带上能不能再验证：schema closure-profiles-0.6 → 0.7，search_study 行新增只读 integrity（state = derivable | non_derivable | incomplete、failures、missing、code_fingerprint = match | stale | absent），盘点顶层新增 study_integrity_layers，replication 块透传全库存 chain_layers。实现来自 search-study 0.54.0 的 study_integrity 模块，代码指纹在一次盘点中只算一次再逐包比较。实测 runtime_data/gapbatch-20seeds 等 27 个项目 101 个包：96 derivable / 5 non_derivable，5 个不可验证包分别是 gapbatch-prefix-fix 的 breast_cancer/iris/wine（带 study.self_hash + evidence.binds_spec 两处不符，即计时字段进入内容哈希那个缺陷的产物）与 study-cli/STUDY-wine、study-demo/STUDY-iris（spec.binds_study 不符）。只读展示，人工门与判定集合一字未动。
- 2026-10-30 · v0.17.1 · status=draft · 盘点 next action 与研究设计一致：canonical_run 的 study_design.audit.status=incomplete 时，next 改为 fix study design; G2 is blocked，而不是继续提示 claim sign；避免页面把一个 G2 被阻断的 run 说成下一步去签 claim。实测 ccfa-gate-probe 的盘点返回该文案；tests.test_closure_profiles 17 项 OK。只读投影文案变化，升 patch。
- 2026-10-30 · v0.17.0 · status=draft · 闭合盘点带出研究设计披露：canonical_run 行新增只读 study_design（status/ccfa_level/blockers），从 run/demo.json 的 modules.study_design.audit 读取；没有 study design 时为 null。schema 升 closure-profiles-0.6，前端 ClosureRow 同步并在 incomplete 时显示“研究设计披露不完整，G2 不应冻结”。实测 ccfa-gate-probe 返回 incomplete/disclosure_incomplete 与前 5 条 blocker；tests.test_closure_profiles 17 项 OK，typecheck 通过。输出契约新增字段，升 minor。
- 2026-10-30 · v0.16.0 · status=draft · 盘点承认已发生的闭合：canonical_run 行新增 has_signature 与 delegated（signature.human_reason 以 [delegated: 开头才算委托签名），closure-report 为 ready 且存在签名时 closure_status 报 signed 而不是 ready，next 改为“去验证已封装 bundle”/“发布本地 bundle”，不再对着已签的 run 继续喊 closure sign；盘点 schema 升 closure-profiles-0.5，前端 ClosureRow 同步并显示 sig=delegated|human|none。实测 runtime_data/autopilot-e2e：autopilot 完成后盘点返回 has_signature=true、delegated=true、closure_status=signed、next=closed locally...；tests.test_closure_profiles 16 项 OK（新增一项），tsc --noEmit 通过。只读投影，无签署语义变化；输出契约新增字段，升 minor。
- 2026-10-30 · v0.15.0 · status=draft · 闭合盘点把待签内容放到读者面前：canonical_run 每条尚未签署的 run 新增只读 claim_draft（status/statement/scope/assertion/reading/command/cwd/boundary），命令路径相对项目根，statement 与 human-reason 只留占位符，签署后该字段变为 null；盘点 schema 升为 closure-profiles-0.4。实测 runtime_data/mcp-loop-demo 返回两条待签 run 的逐字命令，且命令里不含项目绝对路径；tests.test_closure_profiles 15 项 OK（新增一项断言草稿透传、相对路径、签署后消失），test_runtime_api 的 schema 断言同步；tsc --noEmit 通过。只读展示，无签署语义变化；输出契约新增字段，升 minor。
- 2026-10-30 · v0.14.1 · status=draft · 0.14.1（2026-10-30）：闭合盘点里的"不可判定"带上下一步。closure_profiles._study_verdict 的每个比较新增 seeds_for_80pct（来自 study evidence 的规划估算，缺失时为 null，不写 0 冒充），前端 StudyComparison 类型同步，工作台在不可判定行内显示"按当前效应量约需 N 种子才可能判定"，同时补上点估计为负/为零时此前不显示任何解释的空档。实测 runtime_data/power-probe 的盘点返回 25 / 119 / 225 三个值并原样到达页面数据；tsc --noEmit 通过；tests.test_closure_profiles 14 项 OK（新增两项：提示透传、无提示时为 null 而非 0）。无判定语义变化，升 patch。
- 2026-10-30 · v0.14.0 · status=draft · 2026-10-30 · v0.14.0 · status=draft · 项目盘点 replication 摘要新增 power_audit（ladders/decided_at_lower_power/overturned/reversal_rate/per_dataset/reading），工作台 CLOSURE PROFILES 顶部显示"低功效 N 条里 M 条不再成立（反转率 x%）"——把护栏的成本放在结论旁边，而不是埋在报告文件里。另修 study closure --verify-repro 的判据（改比数值而非 study_sha256，见 search-study 0.20.0）。实测反转率 11.1%（27/3）。
- 2026-10-30 · v0.13.0 · status=draft · 2026-10-29 · v0.13.0 · status=draft · study closure 增加两条证据检查且不改任何阻断语义：code.canary_stable（warning，比较 spec.algorithm_canary 与当前重跑的固定对照集）与 code.reproduced（--verify-repro 时重跑本包控制集比较 study_sha256，pass=warning 级说明、fail=blocker）。code.unchanged 仍完全由整文件 code_fingerprint 决定。CLI 新增 study closure --verify-repro。实测 replication-64/studies/iris：同一份报告里 code.unchanged=fail 且 code.reproduced=pass。
- 2026-10-29 · v0.12.0 · status=draft · 2026-10-29 · v0.12.0 · status=draft · 项目盘点 replication 摘要增加 overturned（完整条目：dataset/comparison/reason/decided_at/at_higher_power，目录名为相对包名，不含绝对路径）与 power_ladders 计数；工作台 CLOSURE PROFILES 下新增 overturned 行，把"低功效判定不能签成结论"显示给人看。
- 2026-10-29 · v0.11.0 · status=draft · 2026-10-29 · v0.11.0 · status=draft · 项目级盘点 schema 升到 closure-profiles-0.3：detect_project_profiles 在 search_study 行之外新增 replication 字段（<2 个研究包时为 null），内容由 study_replication.build_replication_report 计算，只保留 design_key/datasets/seed_counts/status/direction/decided_in/generalizes 与 unreplicated 的原因，剥掉绝对路径与逐格区间（页面展示“几个数据集判定”，不复制第二份证据）。runtime 的 /api/project-closures 与 CLI closure profiles 共用该函数，因此没有新增端点。实测 runtime_data/from-idea-check：packages=4，1 个复现组（breast_cancer/iris/wine 各 16 种子）+ 1 个 unreplicated（pipeline 写出的 wine 设计不同），LEAK 检查确认为绝对路径未出现在响应中。契约变化：输出多一个只读字段。
- 2026-10-29 · v0.10.0 · status=draft · 0.10.0（2026-10-29）：盘点与闭包共用同一套 origin 判定。closure_profiles 不再自己算 spec 哈希比较，改为调用 study_claims.origin_state，避免页面显示 bound 而闭包判 stale 的双口径；origin 判定移出 claim 分支，未签署的研究包同样被检查。
- 2026-10-29 · v0.9.0 · status=draft · 0.9.0（2026-10-29）：研究盘点带出想法溯源。search_study 行新增 origin=absent|bound|stale（把 study-origin.json 记录的 study_spec_sha256 与当前 spec 重新算一次比对，--force 重跑即判 stale）、idea_id/idea_title/falsification；closure-report 尚未生成时 dataset 改从 study-spec.json 取（用目录名会把 wine 研究标成 STUDY-IDEA-02）。仍是只读投影：不写、不签、不判真伪。
- 2026-10-29 · v0.8.0 · status=draft · 0.8.0（2026-10-29）：盘点携带结论三态。search_study 行新增 verdict（comparison_verdicts 投影：逐项 state/mean_diff/ci95 与 decidable/undecidable 计数），并把 study_dir 改成项目内相对路径（只读盘点会经 HTTP 返回，绝对路径没有收益只有泄露）；证据包损坏时该行标 available=false 而不是让整份盘点抛错。仍为只读：不签、不改、不判真伪。
- 2026-10-29 · v0.7.0 · status=draft · 0.7.0（2026-10-29）：detect_project_profiles 盘点第三类产物 studies，返回 search_study 条目（closure_status 在已签名时报 signed 而非沿用签名前的 ready_for_human_signature）；guidance 补"功效不足不可关闭为结论"。
- 2026-10-29 · v0.6.0 · status=draft · 0.4.0→0.6.0（2026-10-29）：closure_profiles 增加第三套 profile search_study，绑定 study-spec/study/study-evidence/claim/closure-report/signature 的规范化 JSON 哈希链；闭合条件新增 power.sufficient 与 has_decidable_comparison（功效不足不能关闭为结论）与 code.unchanged（搜索代码指纹变更即阻断引用）；签名要求报告仍为 ready 否则拒绝；study closure --build-lineage/--verify 提供只读 fresh/stale。契约变化：profile 数量与新增检查项。
- 2026-10-28 · v0.5.7 · status=draft · 修复义务台账自动销账：未决项从新报告消失只标 `unverified_disappearance` 并继续阻断；新增 `closure obligations list/resolve/waive`，resolve 需人理由+证据 SHA-256，waive 需人理由；MCP/runtime 仍无签核入口。
- 2026-10-27 · v0.5.6 · status=draft · 若 run 目录存在 `support-panel.json`，closure check 增加 `support_panel_ready`：只有 ready/not_applicable 可通过；needs_human/blocked/partial 或不可读一律 blocked，panel 文件进入 artifact_refs。人签前仍会重跑检查，panel 变化会使旧报告失效。
- 2026-10-27 · v0.5.5 · status=draft · 统一两类 closure profile 词汇：canonical RunCapsule/EA closure report 标 `closure_profile=canonical_run`，本地实验 closure 标 `local_experiment`；新增只读 `closure profiles` 注册表与项目产物盘点；两者都必须人签且 `submission_ready=false`，不得互相冒充。
- 2026-10-26 · v0.5.4 · status=pilot · 新增 append-only closure obligations：失败 check/unresolved slot 生成 `obligations.json`，后续报告可 resolve，复发则 reopened；历史不删除，resolution 绑定报告 SHA-256；postprocess 记录路径与摘要。
- 2026-10-26 · v0.5.3 · status=draft · 新增本地 signer 身份与 HMAC-SHA256 签名：signature 记录 signer/key/scheme/payload hash；publish 验证 HMAC；无 signer 时保留 legacy-unsigned 但明确标注；仍非 PKI/法律签名。
- 2026-10-26 · v0.5.2 · status=draft · 支持预注册 ProtocolCard + protocol-binding 的 capsule 哈希校验；artifact 路径统一 resolve，修复 closure sign 因相对/绝对路径不一致导致的重校验失败。
- 2026-10-25 · v0.5.1 · status=draft · 最小加固：closure 现在读取真实 run-capsule 文件并校验 status；claim.assertions 会从 metrics artifact 重算，不一致直接 blocked。
- 2026-10-25 · v0.5.0 · status=draft · 新增 closure audit：对 pipeline 产物做静态结构审计（S1 span→source、S2/S4 引用、G2/protocol、S5 EA/claim draft、paper 槽位、schematic 图、G5/closure），只判结构一致性，不把人签或 closure 缺失伪装成通过。
- 2026-10-25 · v0.4.0 · status=draft · 补齐证据闭合：protocol/bibliography/result-figure manifest 的伴随文件必须存在并与 demo 一致；bibliography entries 重新哈希；全部可定位证据进入 artifact_refs，使新签名产生可自包含的 bundle
- 2026-10-25 · v0.3.0 · status=draft · 新增不可变证据 bundle：publish 复制并复核 export-manifest 列出的全部证据，写 bundle-manifest，staging+fsync+原子 rename 且拒绝覆盖；verify-bundle 重算字节与哈希；不改变 claim/signature 权限边界
- 2026-10-24 · v0.2.0 · status=draft · 签署门加固：sign 从当前输入重跑 closure，旧报告 checks 不匹配即拒绝；export manifest 绑定 checks 哈希与全部可定位输入文件
- 2026-10-24 · v0.1.3 · status=draft · 最小改进：增加 bibliography_verified 检查；全槽位绑定后 status=ready，人签生成 submission=false 的 export manifest
- 2026-10-24 · v0.1.2 · status=draft · 最小改进：增加 protocol_frozen 检查（status/human_reason/limitation/capsule 哈希）；ChemLab 冻结 protocol 后 9/10 检查通过，仅 citation.related 未决
- 2026-10-24 · v0.1.1 · status=draft · 最小改进：增加 result_figure_provenance 检查（schematic=false、SVG 哈希、EA 引用）；ChemLab 绑定后 8/9 检查通过，仅因 method/limitation/citation 未决 blocked
- 2026-10-24 · v0.1.0 · 初始闭合检查：claim/EA/capsule/paper slot 一致性；pending 槽位阻断导出。
