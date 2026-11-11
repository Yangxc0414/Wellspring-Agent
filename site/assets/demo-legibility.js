/*
 * Shared legibility layer for the Pages demo subpages.
 *
 * These pages are hand-written static HTML that mostly speaks in ids, hashes and
 * internal abbreviations. This script adds three things and changes nothing else:
 *   1. a compact "what is this page / what do these words mean" card + mode note;
 *   2. a plain-language note above every local CLI command block (with copy);
 *   3. an honest "illustration only" treatment for buttons whose only effect is a toast.
 * It never overrides page handlers, never writes to storage and never calls the runtime.
 */
(function () {
  "use strict";

  var MODE_TEXT =
    "静态演示模式：本页数值来自快照 / fixture（固定演示样本），不是实时检索或真实实验；真实运行、人工签核与导出只在本地 CLI 可用。";

  var TERMS = {
    "SPEC": { zh: "模块规格", desc: "每个能力先写「合同」再写代码；改行为必须先改规格，代码不能偷偷越权。" },
    "artifact": { zh: "产物", desc: "流程里生成的文件（span、EA、claim、图、稿件等），按内容哈希互相引用。" },
    "gate": { zh: "人工门 / 门禁", desc: "必须停下来由人决定的检查点；浏览器不会代签、不会自动放行。" },
    "span": { zh: "可定位原文片段", desc: "文献里能指出处的短句；只有全文才生成 span，摘要只算线索。" },
    "EA": { zh: "证据断言", desc: "EvidenceArtifact：把一次 run 的数值封存成可核查的断言，是 claim 的依据。" },
    "claim": { zh: "研究主张", desc: "作者 / PI 在终端核对 EA 后人工签署的结论，不能由浏览器自动生成或代签。" },
    "closure": { zh: "闭合检查", desc: "导出前的一致性检查（引用、来源、覆盖等），未通过就不能生成导出清单。" },
    "RunCapsule": { zh: "运行胶囊", desc: "一次本地执行的完整过程与成本记录；失败也保留，便于独立重跑。" },
    "stale": { zh: "失效", desc: "上游内容变了，依赖它的下游产物不能继续复用，必须重新验证。" },
    "fail-closed": { zh: "失败即锁", desc: "检查没过就默认拒绝导出，而不是「先放行再说」。" },
    "MCP": { zh: "模型上下文协议", desc: "外部 Agent（Qoder / Codex / Zcode / WorkBuddy 等）接入同一套工具的通道；工具表里没有签名或批准按钮。" },
    "host-model": { zh: "宿主模型交接", desc: "没有 API key 时，把生成步骤交给当前 Agent，再把回答读回平台。" },
    "RSI": { zh: "递归自改进", desc: "让系统改进自身的研究流程；本页展示的是受治理的版本台账，不宣称已具备开放式自改进能力。" },
    "fixture": { zh: "固定演示样本", desc: "预置的只读样例数据，用来展示流程；不是真实检索、真实实验或研究结论。" },
    "SIM": { zh: "模拟", desc: "页面上的动作只做演示推演，不会改动文件、不会发起真实连接、不会执行重跑或签名。" },
    "STATIC": { zh: "静态构建", desc: "runtime 在编译时禁用；页面只读随包产物，所有写操作都在本地 CLI。" },
    "provenance": { zh: "溯源", desc: "记录一张图 / 一个数字是从哪次 run、哪份数据生成的。" },
    "pending": { zh: "待处理", desc: "还没满足条件，例如稿件槽位在 EA 到达前保持 pending。" },
    "bound_claim": { zh: "已绑定主张", desc: "稿件的结果槽位已经指向一份人签 claim；人签之前不能标成已绑定。" },
    "slot": { zh: "稿件槽位", desc: "论文里需要填结论的位置（方法 / 主结果 / 图 / 局限 / 引文等）。" },
    "AUC": { zh: "曲线下面积", desc: "一种分类/排序度量；本页的 AUC 交互结果用于检验度量是否有效，不是研究结论。" },
    "raw": { zh: "原始读数", desc: "未经加工的事件计数等量；与 AUC 对照用来判断度量口径是否可靠。" },
    "event-count": { zh: "事件计数", desc: "只统计发生了多少次，不能单独当作效率或机制发现。" },
    "DataCite": { zh: "数据引用元数据", desc: "给数据集附上的标准化引用信息（作者、标识、版本等）。" },
    "StepLedger": { zh: "步骤台账", desc: "记录 RSI 每一步的输入、判定与结果，便于复验。" },
    "lease": { zh: "租约", desc: "一次受约束的执行授权：限定范围、到期即停，越界不执行。" },
    "MetaTracker": { zh: "元追踪器", desc: "跟踪「对改进本身」的观察与判定，与研究对象的数据分开。" },
    "sealed": { zh: "封存复核", desc: "按新协议重新核对已生成的产物，确认没有越过证据边界。" },
    "H1H4": { zh: "假设 H1–H4", desc: "四条待验证的研究假设；页面上明确标注仍是假设，不是已证实结论。" },
    "episode": { zh: "回合 / 片段", desc: "自进化台账里一次完整的「提出→验证→判定」记录。" },
    "lease-state": { zh: "租约状态", desc: "active / confirmed 等表示一次执行授权当前是否被采纳，不是能力结论。" },
    "adopted": { zh: "已采纳", desc: "该次改动通过判定并进入生效世代。" },
    "reverted": { zh: "已回退", desc: "该次改动未通过判定或被撤销，不作为有效版本。" },
    "CONFORMANCE": { zh: "契约一致性", desc: "检查产物是否符合约定的 schema、预算与边界；PASS/FAIL 是自检结果。" },
    "R/P": { zh: "rollouts / sessions", desc: "R=递归展开次数、P=会话数，是预算读数，不是性能或准确率。" },
    "sha256": { zh: "内容哈希", desc: "按文件内容算出的指纹；内容变一个字节，哈希就变，下游随之失效。" },
    "generation": { zh: "世代", desc: "agent 树与平台代码各留一条版本轨道；同树换平台会自动触发复验。" },
    "WIRED": { zh: "已接线", desc: "该模块确实调用了模型；不等于 pipeline 已全面使用模型。" },
    "CONFIG-ONLY": { zh: "仅配置", desc: "只登记了密钥 / 端点，运行时还没有真实消费者。" },
    "KEY-SOURCE": { zh: "密钥来源", desc: "ENV / SESSION 表示从环境变量或当前会话读取，页面不保存密钥。" },
    "TRANSPORT": { zh: "传输方式", desc: "模型请求走哪种协议/端点。" },
    "LOGGING": { zh: "日志范围", desc: "METADATA ONLY 表示只记元数据，不记录提示词正文或结果内容。" },
    "profile": { zh: "模型配置档", desc: "一组模型、温度、上下文长度等参数的命名配置。" },
    "runtime": { zh: "本地运行时", desc: "需要在自己机器上启动的 FastAPI 服务（默认 8787）；静态页面不会连接它。" },
    "STATUS": { zh: "连接状态", desc: "未连接 / 已连接只读；只有启动 runtime 后才有真实读数。" },
    "QUEUE": { zh: "队列", desc: "等待执行的本地任务数量。" },
    "SIGN": { zh: "签署", desc: "CLI / HUMAN 表示只能由人在终端签署，页面没有签核按钮。" },
    "CHECKING": { zh: "检测中", desc: "正在探测本地 runtime 是否可达，是过程状态而不是结果。" },
    "IDLE": { zh: "空闲", desc: "没有正在执行的任务。" },
    "READ-ONLY": { zh: "只读", desc: "只能查看快照，不能写入或触发真实运行。" },
    "claims": { zh: "主张数", desc: "台账里已登记的研究主张数量，不等于已被证实。" },
    "RUN-ID": { zh: "运行 ID", desc: "RUN- 开头：一次本地执行的编号。" },
    "MT-ID": { zh: "模型回合 ID", desc: "MT- 开头：一次宿主模型问答的编号。" },
    "RG-ID": { zh: "委托结果 ID", desc: "RG- 开头：一次外部 Agent 委托的回执编号。" },
    "needs_human": { zh: "需人工", desc: "停在人工门，等待人在终端决定。" },
    "blocked": { zh: "已阻断", desc: "前置条件未满足，不能继续；不是失败，也不是跳过。" },
    "S5_NOT_RUN": { zh: "S5 未执行", desc: "结果阶段还没跑，因此不能生成 EA 或 claim。" },
    "UNTRUSTED": { zh: "不可信输入", desc: "外部工具返回的内容不能当证据，需人工批准后才可引用。" },
    "RUN": { zh: "运行", desc: "查看本次执行的阶段与产物。" },
    "EVIDENCE": { zh: "证据", desc: "查看 span / EA / claim 的引用链。" },
    "EVOLUTION": { zh: "自进化", desc: "查看版本台账与失效复验。" },
    "CTX": { zh: "上下文", desc: "右侧上下文面板的开关。" },
    "NO-API": { zh: "无 API", desc: "静态预览不调用后端，状态只存在浏览器本地。" },
    "scored-verdict": { zh: "评分判定", desc: "按固定口径给候选打的判定分，用于演示度量，不是研究结论。" },
    "FailureRecord": { zh: "失败记录", desc: "一次失败运行的过程留痕；负结果会保留，不改成绿灯叙事。" },
    "manifest": { zh: "导出清单", desc: "允许导出的产物列表；上游失效或人签缺失时会被锁住。" }
  };

  var PAGES = {
    home: {
      summary: "这个站点展示一个受治理的科研智能体：从文献、实验到论文，每个结论都要有出处、过人工门。主页是导览，/app/ 是可操作工作台，其余子页是只读演示。",
      terms: ["SPEC", "EA", "claim", "closure", "RunCapsule", "span", "stale", "fail-closed", "MCP", "fixture", "SIM", "gate"],
      legend: [
        { tone: "info", label: "红色方块 = 人工门（人签）；青色方块 = 自动门；虚线 = 反馈回指" }
      ]
    },
    innovation: {
      summary: "七幕演示把一条研究主线从检索走到论文，重点看证据如何封存、门禁如何阻断、负结果如何保留；页面里的数值都来自固定样本。",
      terms: ["SPEC", "artifact", "gate", "span", "EA", "claim", "closure", "provenance", "pending", "bound_claim", "slot", "AUC", "raw", "event-count", "DataCite", "StepLedger", "lease", "MetaTracker", "sealed", "RSI", "fixture", "SIM", "H1H4"],
      legend: [
        { tone: "info", label: "Q0 / G1 / G2 / S5b / G3 / G5 = 门编号（查询、选想法、批设计、签结果、签导出等）" },
        { tone: "info", label: "EB = 导出包；slots = 稿件槽位；claim draft = 待签主张草稿" },
        { tone: "info", label: "H1–H4 是待验证假设；页面明确「不宣称 RSI」" }
      ]
    },
    rsi: {
      summary: "自进化接缝：agent 树与平台代码各自留痕，上游变化会让旧判定失效并触发复验。这里展示的是受治理的版本台账，不是开放式自改进能力结论。",
      terms: ["RSI", "episode", "lease", "adopted", "reverted", "CONFORMANCE", "R/P", "sha256", "generation", "fixture", "SIM", "STATIC"],
      legend: [
        { tone: "ok", label: "绿 / ok / adopted = 通过并采纳" },
        { tone: "warn", label: "黄 / warn = 待复核或预算边界" },
        { tone: "bad", label: "红 / miss / reverted = 未通过或已回退" }
      ]
    },
    qoder: {
      summary: "接入矩阵：Qoder / Codex / Zcode / WorkBuddy 等外部 Agent 通过同一套 MCP 工具接入；工具表里没有签名或批准按钮，签字永远在人手里。",
      terms: ["MCP", "host-model", "RUN-ID", "MT-ID", "RG-ID", "needs_human", "blocked", "S5_NOT_RUN", "fixture", "SIM", "claim", "closure"],
      legend: [
        { tone: "info", label: "页面上的 RUN- / MT- / RG- 长串是一次历史 smoke 调用的回执 ID，本页不可重放" },
        { tone: "warn", label: "needs_human = 停在人工门；blocked = 前置未满足；NOT_RUN = 阶段尚未执行" }
      ]
    },
    models: {
      summary: "模型网关：哪些模块真的调用了模型、哪些只是配置了密钥；接入 API 不等于 pipeline 已使用模型，也不绕过 claim / EA / 人工门。",
      terms: ["WIRED", "CONFIG-ONLY", "KEY-SOURCE", "TRANSPORT", "LOGGING", "profile", "MCP", "fixture", "SIM"],
      legend: [
        { tone: "ok", label: "WIRED = 已接线（有真实消费者）" },
        { tone: "warn", label: "CONFIG ONLY = 仅配置（还没真实调用）" }
      ]
    },
    live: {
      summary: "本地运行时面板：只有在本机启动 runtime（默认 8787）后才有真实读数，否则显示「未连接」；本页不产生签名或真实实验。",
      terms: ["runtime", "STATUS", "QUEUE", "SIGN", "CHECKING", "IDLE", "READ-ONLY", "episode", "claims", "lease", "SIM"],
      legend: [
        { tone: "ok", label: "绿 = 已连接 / 正常" },
        { tone: "warn", label: "黄 = CHECKING 检测中 / IDLE 空闲（过程状态，不是结果）" },
        { tone: "info", label: "READ ONLY / CLI · HUMAN = 只读；签核只能在终端由人完成" }
      ]
    },
    agent: {
      summary: "旧版 Agent 工作台的静态预览（只读）；正式工作台在 /app/。这里的按钮只做演示，不调用后端、不产生真实 claim。",
      terms: ["RUN", "EVIDENCE", "EVOLUTION", "CTX", "NO-API", "SIM", "fixture", "claim", "gate"],
      legend: [
        { tone: "info", label: "RUN = 运行 / EVIDENCE = 证据 / EVOLUTION = 自进化 / CTX = 上下文面板" },
        { tone: "warn", label: "标注「仅说明」或「（SIM）」的按钮不会改变数据；可用指令见下方清单" }
      ]
    },
    demo: {
      summary: "研究运行控制台（SIM）：用固定样本回放证据链与导出闸门。所有数值是演示数据，负结果与失败判定会原样保留。",
      terms: ["SIM", "fixture", "stale", "EA", "claim", "closure", "span", "scored-verdict", "FailureRecord", "manifest", "bound_claim", "gate"],
      legend: [
        { tone: "warn", label: "标注「仅说明」的按钮点击后只显示一条说明，不会改变数据或执行操作" },
        { tone: "info", label: "红 = 人工门 / 阻断；青 = 自动门；虚线 = 反馈回指" }
      ]
    }
  };

  function make(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function buildGuide(cfg) {
    var section = make("section", "dl-guide");
    section.setAttribute("aria-label", "本页阅读说明");

    var head = make("div", "dl-guide-head");
    head.appendChild(make("span", "dl-tag", "静态演示 · STATIC / SIM"));
    head.appendChild(make("b", "", "这一页在讲什么"));
    head.appendChild(make("span", "dl-readonly", "只读预览 · 不执行操作"));
    section.appendChild(head);

    section.appendChild(make("p", "dl-summary", cfg.summary));
    section.appendChild(make("p", "dl-mode", MODE_TEXT));

    var details = make("details", "dl-glossary");
    details.appendChild(make("summary", "", "本页术语（点击展开中文解释）· " + cfg.terms.length + " 条"));
    var dl = make("dl", "");
    cfg.terms.forEach(function (key) {
      var term = TERMS[key];
      if (!term) return;
      dl.appendChild(make("dt", "", key + " · " + term.zh));
      dl.appendChild(make("dd", "", term.desc));
    });
    details.appendChild(dl);
    section.appendChild(details);

    if (cfg.legend && cfg.legend.length) {
      var legend = make("div", "dl-legend");
      legend.setAttribute("aria-label", "状态与颜色图例");
      cfg.legend.forEach(function (item) {
        var span = make("span", "");
        span.appendChild(make("i", "is-" + item.tone));
        span.appendChild(document.createTextNode(item.label));
        legend.appendChild(span);
      });
      section.appendChild(legend);
    }
    return section;
  }

  function markCliBlocks() {
    var pres = document.querySelectorAll("pre:not([data-dl-cli-done])");
    Array.prototype.forEach.call(pres, function (pre) {
      var text = pre.textContent || "";
      if (!/python -m research_agent|research_agent\.cli/.test(text)) return;
      pre.setAttribute("data-dl-cli-done", "1");
      var note = make("div", "dl-cli-note");
      note.appendChild(make("span", "", "本地 CLI 命令 · 网页不会执行它 · <尖括号> 占位符需替换为实际路径 / ID"));
      var copy = make("button", "dl-cli-copy", "复制");
      copy.type = "button";
      copy.addEventListener("click", function () {
        if (!navigator.clipboard) { copy.textContent = "请手动选中"; return; }
        navigator.clipboard.writeText(text).then(
          function () {
            copy.textContent = "已复制";
            window.setTimeout(function () { copy.textContent = "复制"; }, 1500);
          },
          function () { copy.textContent = "请手动选中"; }
        );
      });
      note.appendChild(copy);
      pre.insertAdjacentElement("beforebegin", note);
    });
  }

  function markInfoOnlyButtons() {
    var buttons = document.querySelectorAll(
      '[data-wb-action="toast"]:not([data-dl-info]), [data-act="toast"]:not([data-dl-info])'
    );
    Array.prototype.forEach.call(buttons, function (button) {
      button.setAttribute("data-dl-info", "1");
      button.classList.add("dl-info-only");
      button.setAttribute("title", "仅说明：静态演示里的示例动作，点击只显示一条说明，不会改变数据或执行操作");
    });
  }

  function mount() {
    if (document.body.getAttribute("data-dl-mounted") === "1") return;
    var page = document.body.getAttribute("data-dl-page") || "";
    var cfg = PAGES[page];
    if (!cfg) return;
    document.body.setAttribute("data-dl-mounted", "1");

    var main = document.querySelector("main") || document.body;
    main.insertBefore(buildGuide(cfg), main.firstChild);
    markCliBlocks();
    markInfoOnlyButtons();

    // Some demo views render their buttons only after an interaction; keep the
    // "illustration only" marking in sync without touching their handlers.
    if (window.MutationObserver) {
      var observer = new MutationObserver(function (records) {
        for (var i = 0; i < records.length; i += 1) {
          if (records[i].addedNodes.length) {
            markCliBlocks();
            markInfoOnlyButtons();
            return;
          }
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }

  window.DemoLegibility = { mount: mount, terms: TERMS, pages: PAGES };
})();
