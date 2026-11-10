---
id: skills
name: 科研技能目录
stage: META
version: 0.15.0
status: pilot
owner: research-agent
inputs:
  - SKILL.md
  - SkillManifest
  - provenance
outputs:
  - SkillManifest
  - SkillRegistrySnapshot
  - SkillRiskReport
  - SkillUsageRecord
  - SkillEvalReport
  - SkillCandidate
  - SkillVersionSnapshot
  - ExternalSkillAdvisory
  - SkillDistillCandidate
  - SkillPack
tools:
  - skills.scan
  - skills.validate
  - skills.list
  - skills.usage
  - skills.eval
  - skills.propose
  - skills.versions
  - skills.invoke
  - skills.trusted_invoke
  - skills.distill
  - skills.pack
gates: []
invariants:
  - 目录层只做扫描/校验，不执行 scripts；只有 CLI 显式 `--trusted-scripts` 才可运行本地脚本，MCP/runtime 不执行
  - external skill invocation 必须 enabled；instruction-only 需要显式 model profile，trusted script 需要显式 opt-in
  - trusted script 以用户本机 OS 权限运行，不是 sandbox；不经过网络代理、凭据隔离或文件隔离
  - trusted script 的 stdin 只含 skill_id/input/context/workdir；可选 `--script-arg` 直接作为 argv 透传（不经 shell）；stdout/stderr 有上限，超时强制终止；结果不是证据
  - 外部 Skill 输出（含脚本 stdout）是不可信 advisory/工具输出，必须记录 usage；不能作为证据或能力增益
  - 蒸馏只接受 enabled 的外部 Skill，必须有 license 与 human_reason；输出 disabled candidate，不自动启用、不自动版本激活
  - 蒸馏复制 SKILL.md、scripts/references/assets 与顶层资源（排除隐藏文件与依赖缓存）并记录逐文件 SHA-256/provenance；不证明质量、不改变 license、不进入 Claim/EA/gate
  - runtime 只执行 4 个 built-in 只读检查，不执行 imported/custom skill
  - 导入技能是不可信 instructions；默认停用，人工检查后再启用
  - allowed-tools 只是声明，不是权限授予；执行能力始终是 not_available
  - name 与 description 必填；缺少任一字段的文件跳过并报告原因
  - 单文件大小、Skill 数量与 instructions 长度有上限；不把超大文件静默截断后当完整技能
  - 技能目录/说明不进入 SourceHit、Span、Claim、EA、gate、closure 或 signature
  - 浏览器导入与 runtime/CLI 目录是两条入口；浏览器不能直接读取绝对主目录路径
  - usage/eval 只是调用与回归证据，不是能力增益
  - imported/custom skill 不可执行，不能伪造行为评测
  - skill 改进候选只能 pending_human，不能自动改写或自动启用
  - 版本激活只能切换到预注册的 built-in handler，且必须 public+hidden eval pass + 人签理由
  - 版本回滚只能回到已有版本；imported/custom skill 不可激活或回滚
---

# 科研技能目录（META）

## Purpose

把本地 `SKILL.md` / Agent Skills 目录变成可审计的技能清单：解析元数据、检测脚本/高风险工具声明、记录 provenance 与内容 hash，并让 CLI/runtime 能查看同一份目录。它不是执行器，也不把“导入了一个技能”写成“系统获得了新能力”。

## Contract

输入：

- `SKILL.md`：目录型技能（`<name>/SKILL.md`）或根目录扁平 `.md`；
- `SkillManifest`：前端对话/导入产生的最小清单（name、description、instructions、tools、source）；
- `provenance`：本地路径或前端 origin。

输出：

- `SkillManifest`: `name/description/instructions/tools/version/license/origin/content_hash/source/enabled/execution=not_available/untrusted/risk_flags/has_scripts`；
- `SkillRegistrySnapshot`: 目录清单、边界与计数；
- `SkillRiskReport`: 由 `risk_flags` 表示（unbounded_tools/shell_capable/write_capable/network_capable/has_scripts）。
- 脚本判定与打分必须用同一个分布：`language_mismatch` 不再按**字符占比**猜语言，而是按
  `_coverage_tokens` 实际使用的**词元构成**判定——输出 `script_share`（artifact 与 rubric 各自的
  CJK 词元占比）与 `dominant_scripts`，主脚本规则为 `share >= 0.5 → zh`、`<= 0.1 → latin`、
  其余 `mixed`；两侧主脚本不同，或任一侧为 `mixed`，都算 `language_mismatch=true`，
  counts 随之降级为 `coverage_confidence="degraded"`（只可当待办清单，不可判优劣），
  无条目可评时为 `unusable`，同脚本且无混排歧义才是 `ok`。
  动因（实测）：一份中文小标题、正文是命令与数字表的签核简报，按字符算是 CJK 5.8%（旧阈值判"英文"），
  按词元算是 CJK 69%，于是"英文 rubric × 中文产物"必然 0 命中而**警告恰恰不触发**——
  而那条警告一直是我判断读数可否采信的闸门。判定依据必须与打分依据同源，否则闸门会在
  最需要它的时候沉默。旧实现见 `search-study §136` 与 `58 §144` 的否证记录。
- `SkillPack` 的窗口语义：`--stage` / `--profile`（`STAGE_PROFILES`，含 `design`=idea+design）在截断**之前**过滤，`checklist` 只是过滤后集合的显示窗口；`checklist_total` 是过滤后、截断前的条数，`limit_applied` 是 `--max-items` 经硬上限裁剪后的实际窗口，`truncated`/裁剪都写入 `warnings`。`skill coverage` 与 `venue audit --skill-pack*` 必须把这三者投影成 `pack_scope`，并在截断时把“部分 rubric”追加进 `boundary`——分母不完整的评分必须自己说出来。
- 三面同参同默认：`DEFAULT_MAX_ITEMS`（=200）是 CLI `skill pack` / `skill coverage` 与 MCP `research_skill_packs` **共用**的 rubric 窗口默认，任何一面单独改默认都会让同一输入在不同面得到不同分母，因此默认值只在这一处定义（MCP 的 inputSchema `default` 必须与之相同，由测试钉住）。`scan` 与 `coverage` 也接受 `pack_root`+`venue` 路由（与 CLI 共用 `resolve_pack_dir`），coverage 输出带 `route`（路由到的 pack 卡片）与 `route_confidence`，低置信度警告两面一致。

规则：

- frontmatter 至少 `name`、`description`；可选 `allowed-tools`、`license`、`version`；
- 单文件 ≤128KB，instructions 截断到 8000 字符并显式标记；最多 100 个技能；
- 候选 `SKILL.md` / 根目录 `.md` 最多读取 200 个；只有 `scripts/` 中实际脚本后缀或同级脚本文件才标记 `has_scripts`，数据文件不算脚本；不读取/执行内容；
- 注册按 name 与 content hash 去重；重复项返回 existing，不覆盖；
- 导入项默认 `enabled=false`；`set_enabled` 只是目录可见性，不改变 `execution=not_available`。

失败/状态：

- 缺 frontmatter/name/description、文件过大、目录不存在：显式 `SkillError` 或 skipped 原因；
- 前端导入失败保留浏览器本地清单，并明确提示 runtime 未连接；
- runtime 只提供 built-in 只读执行端点 `POST /api/skills/{skill_id}/run`（4 个白名单检查），执行结果同时写入 usage receipt；imported/custom 仍不可执行；
- 新增 `SkillUsageRecord`：skill_id/version/task_id/status/checks/artifact_ref/note，只记录使用结果；
- 新增 `SkillEvalReport`：对 4 个 built-in 只读 skill 运行 public/hidden 确定性用例，记录 pass/fail 与 output hash；imported/custom 返回 `not_executable`；
- 新增 `SkillCandidate`：usage 证据 + 人写 patch → RSI `pending_human` 候选；不自动 admission、不自动激活、不写 capability claim；
- 新增 `ExternalSkillAdvisory`：`execution_mode=instruction_only|trusted_script`、skill 版本、输出、usage 与 boundary；instruction-only 只接受 JSON advisory，trusted script 返回 returncode/stdout/stderr/解析后的 output；trusted script 支持 `script_args`（≤20 个、每个 ≤1000 字符、不经 shell）；
- 新增 `SkillDistillCandidate`：`candidate_id/local_name/source_skill_id/source_hash/license/source_url/human_reason/status=candidate/enabled=false/has_scripts/files[]`；`files[]` 覆盖 SKILL.md 与完整 bundled resources，写入 `runtime_data/skill-library/<slug>-<hash8>/`，`distill.json` 与 `SKILL.md` 同目录，并注册 disabled 的 `local-*` 技能；
- 蒸馏要求源 Skill enabled、license 非空、human_reason 非空；同一 source hash 重复蒸馏幂等返回已有 candidate，不覆盖、不自动改状态；
- CLI `skill invoke --distill-on-success` 只在成功调用后蒸馏；蒸馏失败以 `distillation.error` 返回，不把成功调用改写成失败。

## Current Implementation

- `research_agent/skill_registry.py`：`parse_skill_markdown` / `manifest_from_payload` / `SkillRegistryStore` / `scan_skill_directory`；
- `research_agent/paths.py`：`runtime_data/skills.json` 默认绝对路径；
- CLI：`python -m research_agent skill list|scan|enable|disable|delete|export|lint|invoke|distill`；
- Runtime：`GET /api/skills`、`POST /api/skills/import`、`PATCH /api/skills/{id}`、`DELETE /api/skills/{id}`；无 execute/claim/sign；
- 前端：Skills 面板文件夹/.md 导入、`IMPORTED` 标记、默认停用、runtime 在线时同步目录；对话 `/skill-creator` 生成草稿后人工保存；
- 前端按需路由：内置技能使用 `activation=auto/manual/off` 三态，目录常驻但 instructions 不预注入；会话首轮只出计划，检索/设计/冻结/运行/签署/写作动作完成后加载一个对应内置 Skill，后续仅对 inspection 意图按需选择最多一个；导入与自定义技能保持 `manual/off`，不能自动路由。自动加载只复用只读 `skillCardFor` 检查，不执行 scripts 或外部工具；
- `research_agent/skill_lab.py`：`SkillUsageStore`、built-in public/hidden eval、`SkillLab.propose` → RSI pending；
- built-in `protocol-review` v1.1.0：兼容 ProtocolCard 的 `primary_metric`，status=frozen 时额外检查 human_reason / limitation / design_sha256；只读，不代签 G2；
- `SkillVersionStore`：记录 active version、available versions 与 append-only activate/rollback history；`SkillLab.activate` 要求同 skill/version 的 public+hidden eval report pass 且 human_reason；rollback 只回到已有版本；
- runtime `GET /api/skills/versions` 只读；`POST /api/skills/{id}/run` 使用 active version 并把真实版本写入 usage；激活/回滚只在 CLI；
- CLI：`skill usage record|list|summary`、`skill eval`、`skill propose`；runtime：只读 `GET /api/skills/usage`，built-in `POST /api/skills/{skill_id}/run` 会记录 usage；
- Runtime skill run 只允许 `literature-brief` / `hypothesis-triage` / `protocol-review` / `evidence-boundary`；imported/custom 返回 404；
- `research_agent/external_skills.py`：`invoke_external_skill` 支持 no-script advisory 与显式 trusted script；脚本入口优先 `scripts/run.py|run.cmd|run.bat|run.sh|main.py`，否则要求 scripts 下恰好一个脚本；
- `research_agent/skill_distill.py`：`distill_skill` 复制 SKILL.md、`scripts/`、`references/`、`assets/` 与顶层资源，写 per-file hash 与 provenance，注册 disabled candidate；
- MCP `research_skill_invoke` 仍只做 instruction-only；MCP 不提供脚本执行，也不提供自动启用。

## Boundaries

- 目录、runtime 与 MCP 不执行 `scripts/`；只有用户在本机 CLI 显式传 `--trusted-scripts` 才执行；
- trusted script 不是 sandbox：继承 `os.environ`、使用用户 OS 权限、可访问本机文件与网络；不得把这一点描述成隔离执行；
- 不安装依赖、不静默联网；脚本自身的网络/文件行为由用户和脚本共同负责；
- 蒸馏不执行候选、不自动启用；复制脚本不等于审查通过，人工启用前候选始终 disabled；
- 不把导入 instructions 当系统提示自动注入，不自动启用；内置 Skill 的按需路由只是只读检查，不授予工具执行权限；
- 不把 `allowed-tools` 当权限；真正工具调用仍需 runtime 白名单与人工审批；
- 不把技能目录、description 或 risk flags 写入 Claim/EA/gate；
- 浏览器不能直接读 `~/.claude/skills` 绝对路径，必须用户选择文件夹；句柄不持久化。

## Minimal Change Workflow

1. 先改本文件 `Contract` 或 `Current Implementation`；
2. 升 `version`，在 Changelog 追加；
3. 最小化改 `research_agent/skill_registry.py` 及 CLI/runtime 接线；
4. 加/改 `tests/test_skill_registry.py`、runtime 与 CLI 测试；
5. 跑 `python -m unittest discover -s tests -v`，并重新导出工作区快照。

## Changelog

- 2026-11-05 · v0.15.0 · status=pilot · 覆盖度报告升 skill-pack-coverage-0.4，采纳投影契约（60 号文档 D1，实现见 modules/integration v0.42.0）：返回体新增 `generated_at`、`source_fingerprint`（生成这次评分的代码）、`read_only: true`、`base`（两个分母的文字表述，直接取自 v0.14.0 的 comparability）、`provenance`（被评制品的路径/生成指纹/生成时间/语言/脚本状态）。动机是实测：v0.14.0 已经把"基"放进了 comparability，但报告本身仍不带生成时间与生成它的代码指纹，于是一份被转贴的 8/14 依然回答不了"这是对哪份代码、哪一天的评分"；AST 枚举 171 个投影时它也被列为缺 4 个槽位。判定一律未动：covered/missing/overlap/threshold/分母与 v0.14.0 完全一致，并有用例断言"加了这些槽位后 covered 与 matched_demands 不变"。
- 2026-11-05 · v0.14.0 · status=pilot · 覆盖度报告升 skill-pack-coverage-0.3：给每个被引用的比例补上"基"，并让 covered 不再隐藏部分匹配。动因是三次实测（233/235 一族）：(a) 同一研究设计在英文 rubric 下可读作 0/14 或 8/14，差别只来自 README 出自哪一代生成器、以及包内是否混入另一种脚本；(b) AAAI/design 的 "Report uncertainty, variance, and statistical tests when small differences matter" 被判 covered，命中词只有 report/uncertainty/variance，而 statistical test 我们明确不做——一个 covered 标志盖住了"三条要求里只中两条"。改动分两块，都只加披露、不改判定：每条 row 新增 demands / matched_demands / unmet_demand_phrases（按逗号、分号、and、or 词法切分 rubric 句子，并在 boundary 里声明这是"匹配来自哪里"的提示，不是"满足几条要求"的判断）；报告顶层新增 comparability（两个分母的文字表述、threshold、granularity、script 状态与 coverage_confidence、artifact_path / artifact_fingerprint / artifact_generated_at / artifact_language、partial_matches 计数）与 quote_as（一行可照抄的引用串，把比例与它的基绑在一起）。填不到的槽位一律渲染为 unknown 而不是省略——缺席必须可见。artifact 基由 pack_audit.artifact_base 从包内 MANIFEST.json 读 code_fingerprint_recorded / code_fingerprint_now / foreign_script_fields；CLI 与 MCP 两个面共用同一函数（此前两处各自调 coverage_report，现在都传 artifact=bundle_fields 里的基），单文件输入仍返回空 extra，维持 test_skill_packs.BundleInputTest 钉住的"单文件不是包"契约（我第一版给单文件也加了基，被这条既有用例挡住，按它的意图收回）。实测 memory_tradeoff_wine：covered 仍是 8/14（判定未动），quote_as 带上生成指纹 720dfcb2…，partial_matches=4，其中 "Report compute, hardware, data access, model size, and training/inference cost" 的未匹配短语正是 hardware——仪表自己独立复现了 #43（研究包只披露评估次数、不披露硬件），且没有被预先告知。测试 tests/test_coverage_comparability.py 共 15 例（DemandPhrase 2 + PartialMatch 3 + ComparabilityBase 3 + ArtifactBase 5，其中 2 例为方向相反的钉子），含两条方向相反的钉子：covered 且有未匹配短语；以及 overlap 0.333 差 0.007 到阈值而判 missing、却已匹配 3 条短语中的 2 条（说明 demands 披露与 covered 标志互相独立，两个方向都会误导读者）。另有一条断言"传不传 artifact 基，covered/missing/overlap/artifact_ratio 全部不变"，防止披露偷偷变成评分。189 例（skill/pack/venue/coverage/mcp 全集）通过。仍欠：MANIFEST 没有 generated_at，因此 artifact_generated_at 恒为 unknown（#95）；procedural_like 在 design 档漏标投稿动作条目（#88 第二条）本轮未动。
- 2026-11-03 · v0.13.0 · status=pilot · 覆盖度报告新增 ratio_granularity_points（每个被打分值多少个头版百分点），并在 >5 点时输出 ratio granularity 警告。依据：跨两个会议包对同一批完整链研究包实测 design 档只贡献 7 条可打分项，同一制品在 ACL 读作 3/7（0.43）、在 NeurIPS 读作 6/7（0.86），差距完全来自包的措辞而非制品；而既有 thin_denominator 门槛是 5 条，7 条不会被标薄，说明"条数下限"并不能守住一个被引用的比例。该字段只披露度量粒度，不改判定、不删条目、不替换分母。
- 2026-11-03 · v0.12.0 · status=pilot · coverage 报告现在把被打分条目按"文件类要求 / 投稿动作指令"分区（skill-pack-coverage-0.2）：新增每条 procedural_like 标记与 artifact_items/artifact_covered/artifact_missing/artifact_ratio、procedural_* 计数，并在两种比例差 ≥0.1 时给出 mixed denominator 警告。实测 ACL submission 档对完整链研究包：头部 14/38（0.37）与制品侧 14/28（0.50），被重分类的 10 条全是 OpenReview 表单、页数上限、压缩包命名一类人工动作，且 0 条曾被覆盖。分区只并列报告、从不从分母中删除条目，措辞按短语锚定以免把"描述实际做过的脱敏步骤"这类真实缺口误标为纸面工作；分类词法启发式，人类确认前不得据此免责。
- 2026-11-02 · v0.11.0 · status=pilot · v0.11.0 computes the script guard over the same tokens the score uses. language_mismatch was decided by character share while coverage is computed on tokens, and a signing brief with Chinese headings over ASCII tables and commands measured 0.058 by characters and 0.69 by tokens: the guard called it same-script English, stayed silent, and an English rubric scored it 0 of 28 with no warning at all. The guard now reports script_share, dominant_scripts and coverage_confidence (ok / degraded / unusable), flags cross-script pairs and any mixed-script side, and states the shares inside the warning so the reader can check the judgement rather than trust it. Re-scoring shows the correction is narrow and honest: the three Latin-versus-Latin readings this session relied on (study evidence 0 of 7, design 2 of 17, draft 1 of 28) are now labelled ok and stand, while the Chinese-pack reading of an English manuscript and the English-pack reading of the Chinese-headed brief are correctly degraded. _is_zh is gone rather than kept beside the new rule. Five new cases in tests/test_skill_packs.ScriptShareTest; the 25 existing pack cases are unchanged.
- 2026-11-02 · v0.10.0 · status=pilot · v0.10.0 makes the rubric window default shared: DEFAULT_MAX_ITEMS is now the single source for CLI skill pack, CLI skill coverage and the MCP tool, whose default was 60, so one request no longer scores a different number of rubric items depending on which face was knocked on. scan and coverage now accept pack_root plus venue through the same resolve_pack_dir the CLI uses; before this the MCP schema declared both parameters while only the route action read them, which is what calling the tool through Qoder exposed. coverage also reports the route card it scored under on both faces, with the same low confidence warning. The 0.9.2 entry claimed CLI and MCP routing parity: the measurement shows that held only for the route action, and that is recorded here instead of being left as a standing false claim. Four new cases in tests/test_mcp_skill_packs_parity compare the faces against each other.
- 2026-11-01 · v0.9.3 · status=pilot · A bad --pack-root now surfaces as a routing error with the actionable alternative instead of a ValueError traceback: resolve_pack_dir wraps the missing venue index and tells the caller to pass --pack explicitly or point at the root that contains the index.
- 2026-11-01 · v0.9.2 · status=pilot · CLI skill coverage now routes by venue exactly like the MCP tool: --pack-root with --venue resolves a pack directory, the resulting card carries route_confidence and adds a low-confidence warning, and passing neither --pack nor a routable root exits with the usage hint instead of writing a silent 0-of-0 card.
- 2026-11-01 · v0.9.1 · status=pilot · Coverage summaries now break the scored window down by stage. A single number over a mixed profile hid where the gap was: scoring our pre-submission draft against the AAS revision profile looked like 16/130, but the uncovered mass was reviewer-response process items a draft can never satisfy. The buckets account for every scored row.
- 2026-11-01 · v0.9.0 · status=pilot · Rubric coverage now scores the paper itself, not only JSON artifacts: the shared artifact reader accepts Markdown, TeX and plain text on both faces, and a cross-script rubric/artifact pair is flagged whenever it is scored (covered counts across scripts come from shared Latin tokens only, so they are a rough punch list and never a score). Found by scoring our Chinese AAS-track manuscript against the English NeurIPS pack: 0 of 36 with no warning at all.
- 2026-11-01 · v0.8.1 · status=pilot · Coverage now refuses to read as a verdict when it measured nothing: a zero-of-zero report and a zero-coverage report whose rubric language differs from the artifact language both carry explicit warnings plus a language_mismatch field. Found by scoring an English design against the Chinese Acta Electronica Sinica pack, where covered 0 of 11 looked like a harsh review but was term overlap across scripts.
- 2026-11-01 · v0.8.0 · status=pilot · coverage_report 字段收敛为单一真源：stage 不再填 "all"、stages 不再填 ["all"]，未筛选时两者都为空，读一侧不会读到与另一侧矛盾的词汇（此前同一份输出里 stage="all" 而 stages=["idea","design"]）。新增行级 scope_like 与总数：来源为 official-source-map 或标题含"已核验事实/现状说明/学科范围"的条目会被标出，提示这类像要求的范围陈述应由人驳回，启发式不自行判定。动机是宿主内实测 research_skill_packs 时看到的 5 条 AAS 设计项里 1 条是学科范围声明。契约字段语义变化，升 minor。
- 2026-11-01 · v0.7.1 · status=pilot · 补一项回归测试 test_window_never_changes_the_rubric_being_scored：对四种收窄（无过滤/stage/design/submission profile）断言 checklist_total 不随 max_items 变化，且 truncated 恰好等于“过滤后条数 > 窗口”。把 #28 修掉的顺序缺陷钉成不变量，避免以后又把截断放回过滤之前。
- 2026-11-01 · v0.7.0 · status=pilot · scan_pack 新增 stages（阶段 profile 在截断之前过滤）与 checklist_total / limit_applied / profile_stages。此前 --max-items 与 --stage/--profile 的先后顺序是反的：先把 pack 截到窗口再按阶段过滤，导致 skill coverage 报“design 阶段 4 条 actionable”时其实只看过 11 条候选（AAS design 实际 29 条，被静默丢掉 22 条）。现在过滤先于窗口，coverage 输出带 pack_scope（checklist_items / checklist_total / max_items / limit_applied / truncated / warnings），截断与超出硬上限的裁剪都会写进 warnings 与 boundary；新增 design profile（idea+design），评审研究设计时不再把 writing/submission/review 条目算进分母。
- 2026-11-01 · v0.6.8 · status=pilot · scan_pack 新增 navigation 标志：只指向同 pack 其它 skill 的条目（如 Paper shaping: use neurips-writing-style）不再计入 actionable；带实质要求、只是顺带引用兄弟 skill 的条目保留为要求。NeurIPS 实测剔除 7 条指针，AAS 无误杀。
- 2026-11-01 · v0.6.7 · status=pilot · 新增 skill coverage CLI：把任意 JSON artifact（研究设计、计划、草稿）对本地 pack 的 actionable rubric 打分；coverage 增加 near_miss 计数，区分部分披露与完全缺失，并在 boundary 里写明跨语言会低报。
- 2026-11-01 · v0.6.6 · status=pilot · 阶段路由加标题优先规则：标题含 答复/回复/审稿/退修/回应/rebuttal/response/reviewer 的条目直接判为 review，避免回复信条目污染 writing 与 draft profile；AAS 实测 review 13→22、draft profile 由 70 降到 67 条 actionable。
- 2026-11-01 · v0.6.5 · status=pilot · coverage_report 新增 stages/profile 过滤；venue audit 可用 draft/submission/revision profile 将草稿审计限定到相关阶段，减少回复信等跨阶段条目噪声。
- 2026-10-31 · v0.6.4 · status=pilot · skill pack 增加 actionability 启发式：表格行视为要求，现状/背景/为什么等标题与目的性开头视为叙述；coverage 默认只统计 actionable 条目并报告 context_skipped，新增 actionable_counts；仍是 advisory，不改变任何判定。
- 2026-10-31 · v0.6.3 · status=pilot · Skill pack 覆盖度改为中英混合词法：中文三字短语命中即覆盖，英文按词边界匹配；venue 路由按最长中文关键词与英文词边界打分，并给出 high/medium/low 置信度。
- 2026-10-31 · v0.6.2 · status=pilot · skill pack 只返回整份 checklist，无法知道当前稿件覆盖了哪些项；新增 coverage_report：对 pack checklist 做确定性词项覆盖（英文词/CJK 2-3 gram），输出 covered/missing/unmatched、overlap 与 matched_terms。语义边界：covered 只表示相关词出现，不表示要求满足，不改变 status、不产生证据。venue audit 自动附 coverage；新增 --skill-stage。skill pack 7 项测试通过。
- 2026-10-31 · v0.6.1 · status=pilot · skill pack 只能手动指定目录，不能按目标 venue 找到对应 pack；新增 skill route 与 find_venue：读取 shared-resources/journal-selection/venue-index.tsv，按 venue_id/display_name/关键词路由到 pack_dir，返回 pack_exists/profile/source_map；venue audit 增加 --skill-pack-root + --venue 自动附加 pack checklist。路由是词法导航，不是官方分类或 pack 质量结论。新增 3 项测试（精确/中文关键词/CLI+审计自动路由），skill pack 共 7 项通过。
- 2026-10-31 · v0.6.0 · status=pilot · 外部期刊 Skill 仓库有 300 pack/4166 skill，但本仓库只把两个期刊手工投影成固定检查；这等于用硬编码替代了 skill 的机制。新增 skills.pack：扫描任意本地 pack 的 SKILL.md + resources，提取 license/哈希/provenance 与按阶段路由的 checklist；不执行 scripts、不联网、不把 checklist 当证据/Claim/gate。CLI 支持 --stage/--max-items/--output；venue audit 可 --skill-pack 附加 advisory rubric。新增 4 项测试（AAS pack 实测 12 skills/6 resources/MIT）。契约新增 SkillPack 与 CLI，升 minor。
- 2026-10-27 · v0.5.2 · status=pilot · 新增只读 MCP `research_skill_instructions`：Qoder 可直接读取已启用外部 Skill 的 instructions/license/hash 并自行执行；不调用模型、不执行脚本、不返回本地路径。
- 2026-10-27 · v0.5.1 · status=pilot · 新增 `skill journal-verify`：外部期刊 Skill profile 记录 SKILL.md/license 相对路径与 SHA-256，验证源文件未被替换；profile 进入 writer brief 与 journal_style audit，保留 MIT 来源；不执行外部脚本。

- 2026-10-26 · v0.5.0 · status=pilot · 外部 Skill 全权限调用与蒸馏：CLI `skill invoke --trusted-scripts` 在显式 opt-in 下以本机 OS 权限运行 scripts（支持无 shell argv 透传，非 sandbox），`skill distill` 把 enabled + license + human_reason 的外部 Skill 复制为 disabled `local-*` candidate（完整 scripts/references/assets + provenance/per-file hash），`--distill-on-success` 仅在成功调用后沉淀；MCP 仍不执行脚本、不自动启用。
- 2026-10-26 · v0.4.0 · status=pilot · 新增 external skill instruction-only advisory invocation：enabled + 无 scripts + 显式 model profile；不执行工具/脚本/网络/文件，输出不可信 advisory，写 usage；CLI `skill invoke` 与 MCP `research_skill_invoke`。
- 2026-10-26 · v0.3.1 · status=pilot · 新增 `skill lint` 静态 manifest linter：frontmatter/name/description/body 行数、重复名称、markdown 越界链接、scripts 危险调用（eval/exec/os.system/subprocess 等）检查；description 上限对齐 1024；只读，不执行脚本。
- 2026-10-26 · v0.3.0 · status=pilot · Skill 版本治理：新增 SkillVersionStore、版本化 built-in handler 与 CLI version list/activate/rollback；激活要求 public+hidden eval pass 和人签理由，只切换预注册版本，不重写代码；runtime 只读版本并提供 active 版本执行。
- 2026-10-26 · v0.2.1 · status=pilot · protocol-review 1.1.0：同时接受 primary_metric/metric；protocol status=frozen 时检查 human_reason、limitation、design_sha256；仍只读，不签 G2。
- 2026-10-25 · v0.2.0 · status=pilot · 契约扩展：新增 SkillUsageStore、确定性 built-in Skill 评测与 RSI pending 提案；usage/eval 只作过程证据，不自动改 Skill、不自动启用、不写 capability claim。
- 2026-10-25 · v0.1.1 · status=pilot · 前端 Skill 生命周期改为按需：内置技能 `auto/manual/off` 三态、首轮不预加载、动作完成后加载对应只读检查、inspection 意图最多选一个；导入/自定义仍只能手动；执行能力仍为 not_available。
- 2026-10-25 · v0.1.0 · status=pilot · 初始实现：Agent Skills `SKILL.md` 目录扫描、frontmatter 校验、内容 hash、风险标记、默认停用与 CLI/runtime 目录；不执行 scripts，不把目录当证据或能力增益。
