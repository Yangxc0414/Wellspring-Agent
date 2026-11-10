(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const escapeHtml = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const fmt = (n) => new Intl.NumberFormat("zh-CN").format(Number(n) || 0);
  const nowTime = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });

  /* ---------------- nav ---------------- */
  const navLinks = $$(".nav-links a");
  const navSections = navLinks
    .filter((a) => (a.getAttribute("href") || "").startsWith("#"))
    .map((a) => $(a.getAttribute("href")))
    .filter(Boolean);
  if ("IntersectionObserver" in window && navSections.length) {
    const navObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((a) => a.classList.toggle("is-active", a.getAttribute("href") === "#" + entry.target.id));
      });
    }, { rootMargin: "-38% 0px -55% 0px", threshold: 0 });
    navSections.forEach((section) => navObserver.observe(section));
  }

  const menuButton = $("#menu-button");
  const mainNav = $("#nav");
  if (menuButton && mainNav) {
    menuButton.addEventListener("click", () => {
      const open = mainNav.classList.toggle("open");
      menuButton.setAttribute("aria-expanded", String(open));
    });
    mainNav.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        mainNav.classList.remove("open");
        menuButton.setAttribute("aria-expanded", "false");
      }
    });
  }

  const progress = $("#scroll-progress");
  const updateProgress = () => {
    if (!progress) return;
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    progress.style.transform = "scaleX(" + Math.min(1, Math.max(0, window.scrollY / max)) + ")";
  };
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();

  if ("IntersectionObserver" in window) {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("in");
        revealObserver.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.06 });
    $$(".reveal").forEach((el) => revealObserver.observe(el));
  } else {
    $$(".reveal").forEach((el) => el.classList.add("in"));
  }

  /* ---------------- lab ---------------- */
  const FALLBACK_WORKS = [
    {
      id: "https://openalex.org/W3147596910",
      doi: "https://doi.org/10.1038/s41586-021-03406-5",
      title: "Pseudo-halide anion engineering for α-FAPbI3 perovskite solar cells",
      year: 2021, cited: 3074, venue: "Nature",
      authors: ["Jaeki Jeong", "Minjin Kim", "Jongdeuk Seo"], oa: true, abstract: ""
    },
    {
      id: "https://openalex.org/W3002058265",
      doi: "https://doi.org/10.1038/s41560-019-0529-5",
      title: "Consensus statement for stability assessment and reporting for perovskite photovoltaics based on ISOS procedures",
      year: 2020, cited: 1810, venue: "Nature Energy",
      authors: ["Mark Khenkin", "Eugene A. Katz", "Antonio Abate"], oa: true,
      abstract: "Abstract Improving the long-term stability of perovskite solar cells is critical to the deployment of this technology. Despite the great emphasis laid on stability-related investigations, publications lack consistency in experimental procedures and parameters reported. It is therefore challenging to reproduce and compare results and thereby develop a deep understanding of degradation mechanisms. Here, we report a con"
    },
    {
      id: "https://openalex.org/W3088739094",
      doi: "https://doi.org/10.1126/science.abb7167",
      title: "Stable perovskite solar cells with efficiency exceeding 24.8% and 0.3-V voltage loss",
      year: 2020, cited: 1518, venue: "Science",
      authors: ["Mingyu Jeong", "In Woo Choi", "Eun Min Go"], oa: false,
      abstract: "Further improvement and stabilization of perovskite solar cell (PSC) performance are essential to achieve the commercial viability of next-generation photovoltaics. Considering the benefits of fluorination to conjugated materials for energy levels, hydrophobicity, and noncovalent interactions, two fluorinated isomeric analogs of the well-known hole-transporting material (HTM) Spiro-OMeTAD are developed and used as HT"
    },
    {
      id: "https://openalex.org/W4288425348",
      doi: "https://doi.org/10.1126/science.abp8873",
      title: "Inactive (PbI 2 ) 2 RbCl stabilizes perovskite films for efficient solar cells",
      year: 2022, cited: 1449, venue: "Science",
      authors: ["Yang Zhao", "Fei Ma", "Zihan Qu"], oa: false,
      abstract: "In halide perovskite solar cells the formation of secondary-phase excess lead iodide (PbI2) has some positive effects on power conversion efficiency (PCE) but can be detrimental to device stability and lead to large hysteresis effects in voltage sweeps. We converted PbI2 into an inactive (PbI2) 2 RbCl compound by RbCl doping, which effectively stabilizes the perovskite phase. We obtained a certified PCE of 25.6%"
    },
    {
      id: "https://openalex.org/W4394728226",
      doi: "https://doi.org/10.1126/science.adm9474",
      title: "Improved charge extraction in inverted perovskite solar cells with dual-site-binding ligands",
      year: 2024, cited: 1398, venue: "Science",
      authors: ["Hao Chen", "Cheng Liu", "Jian Xu"], oa: true,
      abstract: "Inverted (pin) perovskite solar cells (PSCs) afford improved operating stability in comparison to their nip counterparts but have lagged in power conversion efficiency (PCE). The energetic losses responsible for this PCE deficit in pin PSCs occur primarily at the interfaces between the perovskite and the charge-transport layers. Additive and surface treatments that use passivating ligands usually bind to a single act"
    },
    {
      id: "https://openalex.org/W4206188804",
      doi: "https://doi.org/10.1126/science.abh1885",
      title: "Conformal quantum dot–SnO 2 layers as electron transporters for efficient perovskite solar cells",
      year: 2022, cited: 1354, venue: "Science",
      authors: ["Minjin Kim", "Jaeki Jeong", "Haizhou Lu"], oa: true,
      abstract: "Improvements to perovskite solar cells (PSCs) have focused on increasing their power conversion efficiency (PCE) and operational stability and maintaining high performance upon scale-up to module sizes. We report that replacing the commonly used mesoporous–titanium dioxide electron transport layer (ETL) with a thin layer of polyacrylic acid–stabilized tin(IV) oxide quantum dots (paa-QD-SnO2) on the compact–titanium"
    }
  ];

  const labState = {
    works: [],
    selected: new Set(),
    receipt: null,
    attest: false,
    loading: false,
    mode: "idle"
  };

  const labResults = $("#lab-results");
  const labCount = $("#lab-count");
  const labStatus = $("#lab-status");
  const labLog = $("#lab-log");
  const coverageCard = $("#coverage-card");
  const evidenceList = $("#evidence-list");
  const labClaim = $("#lab-claim");
  const labAttest = $("#lab-attest");
  const labGate = $("#lab-gate");
  const labGateResult = $("#lab-gate-result");
  const labRun = $("#lab-run");

  function addLabLog(text, cls) {
    if (!labLog) return;
    const li = document.createElement("li");
    if (cls) li.className = cls;
    const time = document.createElement("time");
    time.textContent = nowTime();
    const span = document.createElement("span");
    span.textContent = text;
    li.append(time, span);
    labLog.appendChild(li);
    labLog.scrollTop = labLog.scrollHeight;
  }

  function setLabStatus(text) {
    if (labStatus) labStatus.textContent = text;
  }

  function reconstructAbstract(index) {
    if (!index || typeof index !== "object") return "";
    const pairs = [];
    Object.keys(index).forEach((word) => {
      const positions = Array.isArray(index[word]) ? index[word] : [];
      positions.forEach((pos) => pairs.push([pos, word]));
    });
    return pairs.sort((a, b) => a[0] - b[0]).map((p) => p[1]).join(" ").trim();
  }

  function normalizeWork(work) {
    const source = work.primary_location && work.primary_location.source;
    const authors = Array.isArray(work.authorships)
      ? work.authorships.slice(0, 3).map((a) => a.author && a.author.display_name).filter(Boolean)
      : [];
    let doi = work.doi || "";
    if (doi && !/^https?:\/\//i.test(doi)) doi = "https://doi.org/" + doi.replace(/^doi:\s*/i, "");
    return {
      id: work.id || doi || ("work-" + Math.random().toString(36).slice(2)),
      doi,
      title: work.title || "（无标题）",
      year: work.publication_year || "—",
      cited: work.cited_by_count || 0,
      venue: (source && source.display_name) || "未标注来源",
      authors,
      oa: !!(work.open_access && work.open_access.is_oa),
      abstract: reconstructAbstract(work.abstract_inverted_index),
      source: "OpenAlex"
    };
  }

  function dedupe(works) {
    const seen = new Set();
    const out = [];
    works.forEach((work) => {
      const key = (work.doi || work.id || "").toLowerCase();
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push(work);
    });
    return out;
  }

  function renderResults(works) {
    if (!labResults) return;
    if (!works.length) {
      labResults.innerHTML = '<div class="empty"><span class="empty-mark" aria-hidden="true">∅</span><b>没有命中</b><p>换一个更具体的研究主题，或扩大年份范围。OpenAlex 以英文索引为主。</p></div>';
      labCount.textContent = "0 条";
      return;
    }
    labCount.textContent = works.length + " 条";
    labResults.innerHTML = works.map((work) => {
      const checked = labState.selected.has(work.id) ? " checked" : "";
      const selected = labState.selected.has(work.id) ? " is-selected" : "";
      const doi = /^https:\/\/doi\.org\//i.test(work.doi)
        ? '<a class="doi-link" href="' + escapeHtml(work.doi) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(work.doi.replace(/^https:\/\/doi\.org\//, "doi:")) + "</a>"
        : '<span class="doi-link">无 DOI</span>';
      const abs = work.abstract
        ? escapeHtml(work.abstract) + (work.abstract.length >= 400 ? "…" : "")
        : "摘要未在 OpenAlex 索引中；只能登记元数据，不能当作已阅读全文。";
      return '<label class="result-item' + selected + '">' +
        '<input type="checkbox" data-work-id="' + escapeHtml(work.id) + '"' + checked + ' aria-label="选择 ' + escapeHtml(work.title) + '">' +
        '<span>' +
          '<span class="result-title">' + escapeHtml(work.title) + '</span>' +
          '<span class="result-meta"><span>' + escapeHtml(work.year) + '</span><span>' + escapeHtml(work.venue) + '</span><span>被引 ' + fmt(work.cited) + '</span><span>' + escapeHtml(work.authors.join(" / ") || "作者未索引") + '</span></span>' +
          '<span class="result-abs">' + abs + '</span>' +
          '<span class="result-badges">' +
            '<span class="badge live">' + escapeHtml(work.source) + '</span>' +
            (work.oa ? '<span class="badge cached">开放获取</span>' : '<span class="badge sim">非 OA</span>') +
            '<span class="badge design">' + doi + '</span>' +
          '</span>' +
        '</span>' +
      '</label>';
    }).join("");
  }

  function renderCoverage(receipt) {
    if (!coverageCard) return;
    if (!receipt) {
      coverageCard.innerHTML = '<div class="empty small"><b>尚未生成</b><p>覆盖回执记录 query、检索时间、来源、记录数、去重数、纳入/排除数与过滤条件。</p></div>';
      return;
    }
    const rows = [
      ["query", receipt.query, true],
      ["source", receipt.source, false],
      ["retrieved_at", receipt.at, false],
      ["mode", receipt.mode, false],
      ["records_total", fmt(receipt.records), false],
      ["fetched", fmt(receipt.fetched), false],
      ["unique", fmt(receipt.unique), false],
      ["included", fmt(receipt.included), false],
      ["excluded", fmt(receipt.excluded), false],
      ["filters", receipt.filters, true]
    ];
    coverageCard.innerHTML = rows.map(([k, v, wide]) =>
      '<div class="cov-item' + (wide ? " wide" : "") + '"><span>' + escapeHtml(k) + '</span><b>' + escapeHtml(v) + '</b></div>'
    ).join("");
  }

  function renderEvidence() {
    if (!evidenceList) return;
    const selected = labState.works.filter((work) => labState.selected.has(work.id));
    if (!selected.length) {
      evidenceList.innerHTML = '<div class="empty small"><b>未选择证据</b><p>从左侧勾选论文后，这里生成候选证据卡；状态永远是 <code>unverified</code>，直到人工核对。</p></div>';
      labAttest.disabled = true;
      labAttest.textContent = "我已核对摘要与来源";
      labAttest.classList.remove("is-on");
      return;
    }
    evidenceList.innerHTML = selected.map((work, index) => {
      const evId = "EV-" + String(index + 1).padStart(2, "0");
      const abs = work.abstract
        ? escapeHtml(work.abstract.slice(0, 220)) + (work.abstract.length > 220 ? "…" : "")
        : "摘要未索引：仅登记元数据，不能当作已阅读全文。";
      return '<div class="evidence-card">' +
        '<b>' + evId + ' · ' + escapeHtml(work.title) + '</b>' +
        '<p>' + abs + '</p>' +
        '<div class="ev-meta">' +
          '<span class="badge design">' + escapeHtml(work.year) + '</span>' +
          '<span class="badge live">' + escapeHtml(work.source) + '</span>' +
          '<span class="badge warn">unverified</span>' +
          '<span class="badge sim">' + (work.abstract ? "abstract" : "metadata-only") + '</span>' +
        '</div>' +
      '</div>';
    }).join("");
    labAttest.disabled = false;
  }

  function setGateRow(index, text, className) {
    const rows = $$("#lab-gate .gate-row");
    const row = rows[index];
    if (!row) return;
    const b = row.querySelector("b");
    if (!b) return;
    b.textContent = text;
    b.className = className;
  }

  function updateGate() {
    if (!labGate) return;
    const selected = labState.works.filter((work) => labState.selected.has(work.id));
    const claimText = (labClaim.value || "").trim();
    const hasEvidence = selected.length > 0;
    const hasClaim = claimText.length >= 12;
    const hasLocator = hasEvidence && selected.every((work) => work.doi || work.id);
    const attested = labState.attest;

    setGateRow(0, hasEvidence ? "通过 · " + selected.length + " 条" : "未通过", hasEvidence ? "gate-pass" : "gate-fail");
    setGateRow(1, hasClaim ? "通过 · " + claimText.length + " 字" : "未通过 · 至少 12 字", hasClaim ? "gate-pass" : "gate-fail");
    setGateRow(2, attested ? "已核对 · 人工" : "未核对", attested ? "gate-pass" : "gate-wait");
    setGateRow(3, "本页不支持", "gate-warn");

    if (!hasEvidence) {
      labGateResult.className = "gate-result";
      labGateResult.innerHTML = "导出状态：<b>未检查</b>。先选择候选证据。";
      return;
    }
    if (!hasClaim || !hasLocator || !attested) {
      labGateResult.className = "gate-result is-blocked";
      labGateResult.innerHTML = "导出状态：<b>Blocked</b>。缺少人工 claim 或摘要核对；导出不能绕过 Closure。";
    } else {
      labGateResult.className = "gate-result is-review";
      labGateResult.innerHTML = "导出状态：<b>Review required</b>。摘要已核对，但全文 locator 未核验；这只是草稿，仍需作者/PI 签署。";
    }
  }

  function resetLab(clearResults) {
    labState.selected.clear();
    labState.attest = false;
    labState.receipt = null;
    if (clearResults) {
      labState.works = [];
      renderResults([]);
      renderCoverage(null);
    } else {
      renderResults(labState.works);
    }
    if (labClaim) labClaim.value = "";
    renderEvidence();
    updateGate();
    if (labAttest) {
      labAttest.textContent = "我已核对摘要与来源";
      labAttest.classList.remove("is-on");
    }
  }

  function handleSelection(workId, checked) {
    if (!workId) return;
    if (checked) {
      if (labState.selected.size >= 3) {
        setLabStatus("最多选择 3 篇候选证据；请先取消一篇再选择。");
        const input = Array.from(labResults.querySelectorAll('input[data-work-id]')).find((el) => el.getAttribute("data-work-id") === workId);
        if (input) input.checked = false;
        return;
      }
      labState.selected.add(workId);
    } else {
      labState.selected.delete(workId);
    }
    labState.attest = false;
    labAttest.textContent = "我已核对摘要与来源";
    labAttest.classList.remove("is-on");
    renderResults(labState.works);
    renderEvidence();
    updateGate();
  }

  async function runOpenAlex(query, year, limit) {
    const filters = ["title_and_abstract.search:" + query, "type:article"];
    if (year > 0) filters.push("from_publication_date:" + year + "-01-01");
    const url = "https://api.openalex.org/works?filter=" + encodeURIComponent(filters.join(",")) +
      "&sort=" + encodeURIComponent("cited_by_count:desc") +
      "&per-page=" + encodeURIComponent(String(limit)) +
      "&select=" + encodeURIComponent("id,doi,title,publication_year,cited_by_count,authorships,primary_location,open_access,abstract_inverted_index");
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("OpenAlex HTTP " + response.status);
    return response.json();
  }

  async function handleRun(event) {
    if (event) event.preventDefault();
    if (labState.loading) return;
    const query = ($("#lab-query").value || "").trim();
    const year = Number($("#lab-year").value || 0);
    const limit = Number($("#lab-limit").value || 6);
    if (query.length < 3) {
      setLabStatus("请至少输入 3 个字符的研究主题。");
      return;
    }
    labState.loading = true;
    labState.mode = "live";
    labState.selected.clear();
    labState.attest = false;
    labRun.disabled = true;
    labRun.textContent = "检索中…";
    setLabStatus("正在请求 OpenAlex 公共 API。浏览器直连，不经过本站服务器。");
    addLabLog("Scout · 请求 OpenAlex · " + query);
    try {
      const payload = await runOpenAlex(query, year, limit);
      const raw = Array.isArray(payload.results) ? payload.results : [];
      const normalized = raw.map(normalizeWork);
      const unique = dedupe(normalized);
      const valid = unique.filter((work) => work.title && work.title !== "（无标题）");
      labState.works = valid;
      labState.receipt = {
        query,
        source: "OpenAlex /works",
        at: new Date().toLocaleString("zh-CN", { hour12: false }),
        mode: "LIVE PUBLIC",
        records: payload.meta && payload.meta.count ? payload.meta.count : raw.length,
        fetched: raw.length,
        unique: unique.length,
        included: valid.length,
        excluded: raw.length - valid.length,
        filters: (year > 0 ? "from " + year + "; " : "") + "type:article; sort=cited_by_count:desc"
      };
      addLabLog("Scout · 返回 " + raw.length + " 条；命中总数 " + fmt(labState.receipt.records));
      addLabLog("Curator · 去重后 " + unique.length + " 条", "ok");
      addLabLog("Validator · 纳入有效标题 " + valid.length + " 条；排除 " + (raw.length - valid.length) + " 条", "ok");
      addLabLog("Coverage · 回执已生成", "ok");
      renderResults(valid);
      renderCoverage(labState.receipt);
      renderEvidence();
      updateGate();
      setLabStatus("检索完成。共返回 " + raw.length + " 条，去重后 " + unique.length + " 条。勾选 1–3 篇登记候选证据。");
    } catch (error) {
      console.error(error);
      labState.mode = "error";
      addLabLog("Adapter · 请求失败：" + error.message, "err");
      addLabLog("提示：可能是网络、CORS 或速率限制；可加载 2026-10-23 离线快照。", "err");
      setLabStatus("实时检索失败：" + error.message + "。可点击“加载离线快照”继续体验证据登记流程。");
      labResults.innerHTML = '<div class="empty"><span class="empty-mark" aria-hidden="true">!</span><b>实时检索未完成</b><p>请检查网络或稍后重试；也可以加载离线快照。离线快照是 2026-10-23 从 OpenAlex 取回的真实元数据，不是编造结果。</p><button class="btn btn-ghost" type="button" id="lab-offline-inline">加载离线快照</button></div>';
      const inline = $("#lab-offline-inline");
      if (inline) inline.addEventListener("click", loadOffline);
    } finally {
      labState.loading = false;
      labRun.disabled = false;
      labRun.innerHTML = '运行检索 <span aria-hidden="true">→</span>';
    }
  }

  function loadOffline() {
    const works = FALLBACK_WORKS.map((work) => Object.assign({}, work, { source: "OpenAlex 离线快照" }));
    labState.works = dedupe(works);
    labState.selected.clear();
    labState.attest = false;
    if (labClaim) labClaim.value = "";
    if (labAttest) {
      labAttest.textContent = "我已核对摘要与来源";
      labAttest.classList.remove("is-on");
    }
    labState.mode = "cached";
    labState.receipt = {
      query: "perovskite solar cell stability",
      source: "OpenAlex 离线快照",
      at: "2026-10-23",
      mode: "CACHED",
      records: 17141,
      fetched: works.length,
      unique: works.length,
      included: works.length,
      excluded: 0,
      filters: "title_and_abstract.search; from 2020; type:article; sort=cited_by_count:desc"
    };
    addLabLog("Adapter · 载入 2026-10-23 离线快照（真实 OpenAlex 元数据）", "ok");
    addLabLog("Coverage · 使用 CACHED 回执；不是刚刚检索", "ok");
    renderResults(labState.works);
    renderCoverage(labState.receipt);
    renderEvidence();
    updateGate();
    setLabStatus("已加载离线快照：6 条真实 OpenAlex 元数据，检索时间 2026-10-23。它不是实时结果，页面已标记 CACHED。");
  }

  const labForm = $("#lab-form");
  if (labForm) labForm.addEventListener("submit", handleRun);
  if (labResults) {
    labResults.addEventListener("change", (event) => {
      const input = event.target.closest('input[type="checkbox"][data-work-id]');
      if (!input) return;
      handleSelection(input.getAttribute("data-work-id"), input.checked);
    });
  }
  if (labClaim) labClaim.addEventListener("input", updateGate);
  if (labAttest) {
    labAttest.addEventListener("click", () => {
      if (!labState.selected.size) return;
      labState.attest = !labState.attest;
      labAttest.textContent = labState.attest ? "已核对（点击取消）" : "我已核对摘要与来源";
      labAttest.classList.toggle("is-on", labState.attest);
      updateGate();
    });
  }
  const labCheck = $("#lab-check");
  if (labCheck) labCheck.addEventListener("click", updateGate);
  const labReset = $("#lab-reset");
  if (labReset) labReset.addEventListener("click", () => {
    resetLab(true);
    addLabLog("UI · 已清空本次证据登记");
    setLabStatus("已清空。可以重新运行检索，或加载离线快照。");
  });
  const labOffline = $("#lab-offline");
  if (labOffline) labOffline.addEventListener("click", loadOffline);
  $$(".preset").forEach((button) => {
    button.addEventListener("click", () => {
      const input = $("#lab-query");
      if (input) input.value = button.getAttribute("data-query") || "";
    });
  });
  if (labResults) {
    renderResults([]);
    renderCoverage(null);
    renderEvidence();
    updateGate();
  }

  /* ---------------- case ---------------- */
  const CASE_STEPS = [
    {
      badge: "FAILED", badgeClass: "danger", id: "RUN-014", title: "Run 2 未过门槛",
      body: "复现运行的判定未达到冻结协议中的门槛。系统不创建 result_claim，而是把失败原因与证据缺口登记到影响队列。",
      kv: [["artifact", "RUN-014 · Verdict: fail"], ["证据缺口", "缺少 EA(source=rerun)；基线未复现"], ["处置", "回到 P3 修订协议，或降级为探索性结果"], ["导出", "Blocked"]]
    },
    {
      badge: "STALE", badgeClass: "cached", id: "CLM-07", title: "结果 claim 失效",
      body: "依赖 Run 2 的结果 claim 被标记为 stale。它不能继续支撑稿件中的结果句，也不能被新句子引用。",
      kv: [["artifact", "CLM-07 · result_claim"], ["原因", "支撑 EA 缺失 / 基线未复现"], ["下游", "S-12 句槽、FIG-03 图 3"], ["处置", "重跑、改写或复核，三选一"]]
    },
    {
      badge: "BLOCKED", badgeClass: "danger", id: "S-12", title: "结果句槽阻断",
      body: "S-12 绑定 CLM-07。claim 失效后，句槽进入 blocked；编辑可以继续写，但该句不能进入导出。",
      kv: [["artifact", "MS-S12 · Sentence"], ["绑定", "S-12 → CLM-07 → RUN-014"], ["状态", "blocked"], ["导出", "Blocked"]]
    },
    {
      badge: "STALE", badgeClass: "cached", id: "FIG-03", title: "图 3 依赖失效",
      body: "图 3 的误差棒来自 Run 2。运行失效后，图注与数据源都进入 stale；不能只改图注蒙混过关。",
      kv: [["artifact", "FIG-03 · Figure"], ["依赖", "RUN-014 · 数据表 DT-02"], ["状态", "stale"], ["处置", "重跑并重绘，或删除该图"]]
    },
    {
      badge: "IMPACT", badgeClass: "design", id: "CS-009", title: "影响闭包与处置",
      body: "ChangeSet 计算依赖闭包：3 个对象需要处置。系统不自动改稿，只分派任务并记录谁在何时处理。",
      kv: [["artifact", "CS-009 · ImpactClosure"], ["受影响", "CLM-07 / S-12 / FIG-03"], ["处置", "rerun / rewrite / recheck"], ["状态", "等待人工确认"]]
    },
    {
      badge: "EXPORT", badgeClass: "danger", id: "EXP-02", title: "导出被阻断",
      body: "Closure 检查发现未解析槽位、stale claim 与缺 EA。导出被阻断；作者/PI 看到的是闭包报告与未解决项，不是“已完成”。",
      kv: [["artifact", "EXP-02 · ExportManifest"], ["阻断项", "1 个 blocked 槽位；1 个 stale claim"], ["状态", "ExportBlocked"], ["下一步", "完成处置并重新闭合，再签署"]]
    }
  ];

  const caseDetail = $("#case-detail");
  function renderCase(index) {
    if (!caseDetail) return;
    const step = CASE_STEPS[index] || CASE_STEPS[0];
    caseDetail.innerHTML = '<div class="case-detail-top"><span class="badge ' + step.badgeClass + '">' + escapeHtml(step.badge) + '</span><span class="mono">' + escapeHtml(step.id) + '</span></div>' +
      '<h3>' + escapeHtml(step.title) + '</h3><p>' + escapeHtml(step.body) + '</p><dl class="kv">' +
      step.kv.map(([k, v]) => '<div><dt>' + escapeHtml(k) + '</dt><dd>' + (v === "Blocked" || v === "ExportBlocked" ? '<b class="text-danger">' + escapeHtml(v) + "</b>" : escapeHtml(v)) + '</dd></div>').join("") +
      '</dl>';
  }
  $$(".case-step").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".case-step").forEach((b) => b.classList.remove("is-active"));
      button.classList.add("is-active");
      renderCase(Number(button.getAttribute("data-step")));
    });
  });
  if (caseDetail) renderCase(0);

  /* ---------------- agents ---------------- */
  const AGENTS = {
    conductor: {
      badge: "CONDUCTOR", code: "role:conductor", name: "Conductor · 编排者",
      desc: "编译任务、选择技能、分配工作、记录状态。它掌握“这次做哪些能力”，但不写 claim、不改稿、不代替 Judge。",
      input: "任务 brief、能力图、预算", output: "WorkflowRun、分派、状态事件", no: "写 claim、改稿件、代替 Judge"
    },
    scout: {
      badge: "SCOUT", code: "role:scout", name: "Scout · 检索与阅读",
      desc: "并行执行多源检索、筛选、去重与 span 定位。它把来源变成可核对的证据候选，但不判断 claim 是否成立。",
      input: "QuerySpec、来源权限、停止条件", output: "SourceHit[]、Span[]、CoverageReceipt", no: "把摘要当全文、写 claim、跳过覆盖回执"
    },
    builder: {
      badge: "BUILDER", code: "role:builder", name: "Builder · 设计与写作",
      desc: "写协议、草稿与图表。它只能引用已有 claim；没有 claim 支持的句子必须标 unsupported。",
      input: "已确认 claim、槽位、体裁模板", output: "Protocol、Draft、Figure", no: "新增事实、创建 claim、绕过槽位"
    },
    executor: {
      badge: "EXECUTOR", code: "role:executor", name: "Executor · 复现执行",
      desc: "在隔离环境里跑冻结的 TaskSpec，产出 RunCapsule 与 artifact。它不解释结果，也不改判据。",
      input: "冻结 TaskSpec、环境、预算", output: "RunCapsule、Artifact、成本", no: "改判据、读隐藏答案、直接写结果 claim"
    },
    judge: {
      badge: "JUDGE", code: "role:judge", name: "Judge · 独立判定",
      desc: "用 rubric 对 RunCapsule 做独立判定，产出 Verdict 与 EA。Work 不能修改 Judge，也不能跳过干净重跑。",
      input: "RunCapsule、rubric、基线", output: "Verdict、EA(source=rerun)", no: "被 Work 修改、复用未重跑的结果"
    },
    auditor: {
      badge: "AUDITOR", code: "role:auditor", name: "Auditor · 独立审计",
      desc: "只读全链路 artifact，检查结构闭合与论证完整性。它可以阻断导出，但不能改稿、不能生成 claim。",
      input: "Claim、EA、Slot、Figure、导出清单", output: "审计报告、阻断/放行建议", no: "改稿、生成 claim、代替人工签署"
    },
    human: {
      badge: "HUMAN", code: "role:human", name: "Human signer · 作者 / PI",
      desc: "科学决策、实验安全、署名与最终责任。AI 使用、未解决项与限制随包导出，责任不转交。",
      input: "闭包报告、未解决项、成本账本", output: "签署 / 拒绝、责任记录", no: "把责任转交给模型"
    }
  };

  const agentDetail = $("#agent-detail");
  function selectAgent(key) {
    const agent = AGENTS[key] || AGENTS.conductor;
    $$(".agent-node").forEach((node) => node.classList.toggle("is-active", node.getAttribute("data-agent") === key));
    $$(".role-card").forEach((card) => card.classList.toggle("is-active", card.getAttribute("data-agent") === key));
    if (!agentDetail) return;
    $("#agent-badge").textContent = agent.badge;
    $("#agent-code").textContent = agent.code;
    $("#agent-name").textContent = agent.name;
    $("#agent-desc").textContent = agent.desc;
    $("#agent-in").textContent = agent.input;
    $("#agent-out").textContent = agent.output;
    $("#agent-no").textContent = agent.no;
  }
  $$(".agent-node").forEach((node) => {
    node.addEventListener("click", () => selectAgent(node.getAttribute("data-agent")));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectAgent(node.getAttribute("data-agent"));
      }
    });
  });
  $$(".role-card").forEach((card) => {
    card.addEventListener("click", () => selectAgent(card.getAttribute("data-agent")));
  });
  if (agentDetail) selectAgent("conductor");

  /* ---------------- skills ---------------- */
  const SKILLS = {
    "SK-01": {
      name: "检索式生成", version: "v1.2", scope: "通用检索 · 中文核刊 / 申请书",
      tools: "Read / WebSearch", perms: "read:project, net:academic",
      evidence: "输出必须带 query、date、source、coverage；不得写 claim",
      verify: "不验证数据库覆盖；只生成检索式与召回估计",
      test: "3/3", artifact: "QUERY-SPEC", state: "pilot"
    },
    "SK-02": {
      name: "统计结果复现", version: "v0.9", scope: "统计复现 · 给定脚本与数据",
      tools: "Bash / Read / Write", perms: "read:run, exec:docker",
      evidence: "必须绑定 RunCapsule + EA；不得解释实验设计",
      verify: "不验证实验设计；只复现给定脚本与数据",
      test: "1/2", artifact: "RUN-CAPSULE", state: "idle"
    },
    "SK-03": {
      name: "中文核刊结果段", version: "v1.1", scope: "中文核刊 · 结果段",
      tools: "Read / Write", perms: "read:claims, write:draft",
      evidence: "必须绑定 confirmed run + EA；不得新增 claim",
      verify: "不验证论证完整性；只检查槽位与 claim 绑定",
      test: "2/2", artifact: "MS-S12-draft", state: "idle"
    },
    "SK-04": {
      name: "图表一致性检查", version: "v1.0", scope: "图表核对 · 结果图 / 表",
      tools: "Read", perms: "read:figure, read:claims",
      evidence: "输出差异清单；不得改图或改 claim",
      verify: "不验证统计正确性；只检查图注/坐标/单位与 claim 一致",
      test: "2/2", artifact: "FIG-AUDIT", state: "idle"
    }
  };
  const skillState = {};
  Object.keys(SKILLS).forEach((id) => { skillState[id] = SKILLS[id].state; });
  let currentSkill = "SK-01";
  const skillLog = $("#skill-log");
  const skillNote = $("#skill-note");

  function addSkillLog(text) {
    if (!skillLog) return;
    const li = document.createElement("li");
    const time = document.createElement("time");
    time.textContent = nowTime();
    const span = document.createElement("span");
    span.textContent = text;
    li.append(time, span);
    skillLog.appendChild(li);
    skillLog.scrollTop = skillLog.scrollHeight;
  }

  function updateSkillCardState(id) {
    const card = document.querySelector('.skill-card[data-skill="' + id + '"]');
    if (!card) return;
    const badge = card.querySelector(".skill-top .badge");
    if (badge) {
      badge.textContent = skillState[id];
      badge.className = "badge " + (skillState[id] === "active" ? "live" : skillState[id] === "revoked" ? "danger" : "sim");
    }
  }

  function selectSkill(id) {
    currentSkill = id;
    const skill = SKILLS[id];
    $$(".skill-card").forEach((card) => card.classList.toggle("is-active", card.getAttribute("data-skill") === id));
    if (!skill) return;
    $("#skill-detail-title").textContent = id + " · " + skill.name;
    const stateBadge = $("#skill-state");
    stateBadge.textContent = skillState[id];
    stateBadge.className = "badge " + (skillState[id] === "active" ? "live" : skillState[id] === "revoked" ? "danger" : "sim");
    $("#sk-version").textContent = skill.version;
    $("#sk-scope").textContent = skill.scope;
    $("#sk-tools").textContent = skill.tools;
    $("#sk-perms").textContent = skill.perms;
    $("#sk-evidence").textContent = skill.evidence;
    $("#sk-verify").textContent = skill.verify;
    $("#sk-test").textContent = skill.test;
    $("#sk-artifact").textContent = skill.artifact;
  }

  $$(".skill-card").forEach((card) => {
    card.addEventListener("click", () => selectSkill(card.getAttribute("data-skill")));
  });
  const skillLoad = $("#skill-load");
  if (skillLoad) skillLoad.addEventListener("click", () => {
    const id = currentSkill;
    if (skillState[id] === "active") {
      addSkillLog(id + " 已 active；重复加载不改变租约");
      return;
    }
    skillState[id] = "pilot";
    updateSkillCardState(id);
    selectSkill(id);
    addSkillLog(id + " manifest 校验通过，加载为 pilot；dry-run " + SKILLS[id].test);
    if (skillNote) skillNote.textContent = "已加载为 pilot；仅当前项目可见，dry-run 通过后才可 active。";
  });
  const skillRun = $("#skill-run");
  if (skillRun) skillRun.addEventListener("click", () => {
    const id = currentSkill;
    if (skillState[id] === "idle" || skillState[id] === "revoked") {
      addSkillLog(id + " 未处于 pilot/active；请先加载，不能直接运行");
      return;
    }
    skillState[id] = "active";
    updateSkillCardState(id);
    selectSkill(id);
    addSkillLog(id + " 运行完成 → artifact " + SKILLS[id].artifact + "；未创建 claim");
    if (skillNote) skillNote.textContent = "运行只产出 artifact；claim 仍由 Evidence 创建，导出仍过 Closure 硬门。";
  });
  const skillRevoke = $("#skill-revoke");
  if (skillRevoke) skillRevoke.addEventListener("click", () => {
    const id = currentSkill;
    if (skillState[id] === "idle") {
      addSkillLog(id + " 未加载；无需撤销");
      return;
    }
    skillState[id] = "revoked";
    updateSkillCardState(id);
    selectSkill(id);
    addSkillLog(id + " 已撤销；依赖 artifact 进入复核队列（SIM）");
    if (skillNote) skillNote.textContent = "撤销不是删一行：Impact 重新计算依赖闭包，依赖产物进入复核。";
  });
  if (skillLog) selectSkill("SK-01");

  /* ---------------- digest ---------------- */
  async function initDigest() {
    const body = $("#digest-body");
    if (!body) return;
    try {
      const response = await fetch("./data/digest.json", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const digest = await response.json();
      const queries = Array.isArray(digest.queries) ? digest.queries : [];
      const total = queries.reduce((sum, q) => sum + (Array.isArray(q.works) ? q.works.length : 0), 0);
      const when = digest.generated_at ? new Date(digest.generated_at) : null;
      const whenText = when && !isNaN(when.getTime()) ? when.toLocaleString("zh-CN", { hour12: false }) : (digest.generated_at || "未知时间");
      const rows = queries.map((q) => {
        const works = (q.works || []).slice(0, 3);
        return '<div class="digest-query"><b>' + escapeHtml(q.label || q.id || q.query) + '</b><div>' +
          '<div class="digest-meta"><span>query: ' + escapeHtml(q.query || "—") + '</span><span>total_hits: ' + fmt(q.total_hits || 0) + '</span><span>returned: ' + fmt(q.returned || works.length) + '</span></div>' +
          '<ul>' + works.map((w) => {
            const title = escapeHtml(w.title || "（无标题）");
            const link = /^https:\/\/doi\.org\//i.test(w.doi || "") ? '<a href="' + escapeHtml(w.doi) + '" target="_blank" rel="noopener noreferrer">' + title + '</a>' : title;
            return '<li>' + link + ' <span class="mono">' + escapeHtml(w.year || "") + '</span></li>';
          }).join("") + '</ul></div></div>';
      }).join("");
      body.innerHTML = '<div class="digest-meta"><span>generated_at: ' + escapeHtml(whenText) + '</span><span>mode: ' + escapeHtml(digest.mode || "CACHED") + '</span><span>queries: ' + fmt(queries.length) + '</span><span>works: ' + fmt(total) + '</span><span>source: ' + escapeHtml(digest.source || "OpenAlex") + '</span></div>' +
        '<div class="digest-empty">以上为随站点打包的公开元数据快照，不是实时检索，也不是本研究产出的结论；精确计数只反映 OpenAlex 当时的索引状态。</div>' +
        (rows || '<span class="digest-empty">digest 中没有查询结果。</span>') +
        (Array.isArray(digest.errors) && digest.errors.length ? '<div class="digest-empty">部分查询失败：' + digest.errors.map((e) => escapeHtml(e.id + " — " + e.message)).join("；") + '</div>' : "") +
        '<div><a class="doi-link" href="./data/digest.json" target="_blank" rel="noopener noreferrer">查看 digest.json</a></div>';
    } catch (error) {
      body.innerHTML = '<span class="digest-empty">尚未生成 digest.json（' + escapeHtml(error.message) + '）。启用 <code>refresh-digest.yml</code> 后，这里会出现带时间戳的公开检索结果；没有运行时不伪造数据。</span>';
    }
  }

  /* ---------------- app shell navigation ---------------- */
  const appViewTitle = $("#app-view-title");
  const appFullLink = $("#app-full-link");
  const appLoader = $("#app-loader");
  const appContext = $(".appbar-context");
  const appViews = $$(".app-main .view");
  const sideItems = $$(".side-item[data-view]");
  let appLoaderTimer = null;
  function pulseAppLoader(ms) {
    if (!appLoader) return;
    clearTimeout(appLoaderTimer);
    appLoader.classList.add("is-on");
    appLoaderTimer = setTimeout(function () { appLoader.classList.remove("is-on"); }, ms || 520);
  }
  function pulseAppContext() {
    if (!appContext) return;
    appContext.classList.remove("is-switching");
    void appContext.offsetWidth;
    appContext.classList.add("is-switching");
    setTimeout(function () { appContext.classList.remove("is-switching"); }, 340);
  }
  const VIEW_TITLES = {
    intake: "接入项目",
    strategy: "策略流程图",
    functions: "功能地图",
    chain: "证据链",
    case: "变更回放",
    agents: "多智能体",
    skills: "技能运行时",
    lab: "真实检索",
    deploy: "部署",
    docs: "文档"
  };
  function showAppView(target, mode) {
    appViews.forEach((view) => view.classList.toggle("is-active", view.id === target));
    sideItems.forEach((item) => {
      const matches = item.getAttribute("data-view") === target &&
        (!item.getAttribute("data-mode") || item.getAttribute("data-mode") === mode);
      item.classList.toggle("is-active", matches);
    });
    const view = document.getElementById(target);
    if (view) view.scrollTop = 0;
    const isDemo = target === "demo";
    if (appViewTitle) appViewTitle.textContent = isDemo ? "演示台" : (VIEW_TITLES[target] || "Research Agent");
    pulseAppLoader();
    pulseAppContext();
    if (isDemo && mode) switchDemoMode(mode);
    if (appFullLink) appFullLink.href = isDemo ? "./demo/#" + mode : "./demo/#console";
    if (isDemo && mode === "console") {
      setTimeout(function () { maybeAutoplayConsole(); }, 360);
    }
  }
  sideItems.forEach((item) => {
    item.addEventListener("click", () => showAppView(item.getAttribute("data-view"), item.getAttribute("data-mode")));
  });
  $$(".brand[data-view]").forEach((brand) => {
    brand.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      showAppView(brand.getAttribute("data-view"), brand.getAttribute("data-mode"));
    });
  });

  function applyHashView() {
    const h = (location.hash || "").replace(/^#/, "");
    const t = document.getElementById(h);
    if (t && t.classList.contains("view")) showAppView(h);
  }
  applyHashView();
  window.addEventListener("hashchange", applyHashView);

  $$(".flow-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.getAttribute("data-flow");
      $$(".flow-tab").forEach((t) => {
        const on = t.getAttribute("data-flow") === key;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      $$(".flow-pane").forEach((p) => p.classList.toggle("is-active", p.getAttribute("data-flow-pane") === key));
    });
  });

  const smbToggle = $("#smb-toggle");
  const smbDetail = $("#smb-detail");
  if (smbToggle && smbDetail) {
    smbToggle.addEventListener("click", () => {
      const open = smbDetail.hidden;
      smbDetail.hidden = !open;
      smbToggle.setAttribute("aria-expanded", open ? "true" : "false");
      smbToggle.textContent = open ? "收起" : "详情";
    });
  }

  const presentBtn = $("#present-btn");
  const presentExit = $("#present-exit");
  function postDemoFocus(on) {
    if (!demoFrame || !demoFrame.contentWindow) return;
    try {
      demoFrame.contentWindow.postMessage({ type: "research-agent:focus", on: !!on }, location.origin);
    } catch (error) {}
  }
  function enterPresent() {
    showAppView("demo", "console");
    document.body.classList.add("present");
    setTimeout(function () { postDemoFocus(true); }, 80);
    setTimeout(function () { postDemoFocus(true); }, 480);
  }
  function exitPresent() {
    document.body.classList.remove("present");
    postDemoFocus(false);
  }
  if (presentBtn) presentBtn.addEventListener("click", enterPresent);
  if (presentExit) presentExit.addEventListener("click", exitPresent);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("present")) exitPresent();
  });

  /* ---------------- project intake ---------------- */
  const intakeReport = $("#intake-report");
  const intakeStatus = $("#intake-status");
  const folderInput = $("#repo-folder");
  const repoUrlInput = $("#repo-url");
  const goalInput = $("#intake-goal");
  const goalCount = $("#goal-count");
  const folderNote = $("#folder-note");
  const intakeScanBtn = $("#intake-scan");
  const readUrlBtn = $("#read-url");
  let intakeProfile = null;
  let stagedProfile = null;
  let intakeMode = "folder";
  let intakeScanBusy = false;
  let intakeScanToken = 0;

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function setIntakeFlow(step) {
    $$(".intake-step").forEach(function (el, i) {
      el.classList.toggle("is-done", i < step);
      el.classList.toggle("is-active", i === step);
      if (i === step) el.setAttribute("aria-current", "step");
      else el.removeAttribute("aria-current");
    });
  }

  function setIntakeBusy(busy) {
    intakeScanBusy = busy;
    if (intakeScanBtn) {
      intakeScanBtn.classList.toggle("is-busy", busy);
      intakeScanBtn.setAttribute("aria-busy", String(busy));
      const label = intakeScanBtn.querySelector(".btn-label");
      if (label) label.textContent = busy ? "正在体检" : "开始体检";
    }
    if (readUrlBtn) readUrlBtn.disabled = busy;
  }

  function syncGoalCount() {
    if (!goalInput || !goalCount) return;
    goalCount.textContent = goalInput.value.length + " / 160";
    const value = goalInput.value.trim();
    $$("[data-goal]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-goal") === value);
    });
  }

  function scanningShell(name, note) {
    const title = escapeHtml(name || "项目");
    return '<div class="intake-scanning ir-cascade">' +
      '<div class="scanx-head"><span class="panel-kicker">03 / READ-ONLY SCAN</span><span class="badge sim">READING SIGNALS</span></div>' +
      '<div class="scanx-title"><h3>正在读取项目结构。</h3><p>' + escapeHtml(note || "只读文件名与大小；不打开内容。") + '</p></div>' +
      '<ol class="scanx-steps" id="scanx-steps">' +
        '<li class="scanx-step" data-scan-step="0"><i>01</i><div><b>读取文件名与目录</b><span>建立只读结构清单，不上传内容</span></div><em>排队</em></li>' +
        '<li class="scanx-step" data-scan-step="1"><i>02</i><div><b>枚举可复现性信号</b><span>测试 / 环境锁 / 数据 / 许可证 / CI</span></div><em>排队</em></li>' +
        '<li class="scanx-step" data-scan-step="2"><i>03</i><div><b>生成候选研究方向</b><span>把结构缺口转成可证伪假设与主指标</span></div><em>排队</em></li>' +
      '</ol>' +
      '<div class="scanx-meter"><i id="scanx-meter"></i></div>' +
      '<div class="scanx-foot"><span><i class="dot dot-sim"></i>只读扫描 · 不上传 · 不执行</span><span>' + title + '</span></div>' +
    '</div>';
  }

  function setScanProgress(step) {
    const rows = $$("#scanx-steps .scanx-step");
    rows.forEach(function (row, i) {
      const state = row.querySelector("em");
      row.classList.toggle("is-done", i < step);
      row.classList.toggle("is-active", i === step);
      if (state) state.textContent = i < step ? "完成" : (i === step ? "进行中" : "排队");
    });
    const meter = $("#scanx-meter");
    if (meter) meter.style.width = [18, 56, 84][Math.max(0, Math.min(2, step))] + "%";
  }

  function countUp(node, target, ms) {
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      node.textContent = String(target);
      return;
    }
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = String(Math.round(target * eased));
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  const EXT_LANG = {
    py: "Python", ipynb: "Notebook", js: "JavaScript", ts: "TypeScript", tsx: "TypeScript",
    jsx: "JavaScript", java: "Java", go: "Go", rs: "Rust", c: "C/C++", cpp: "C/C++",
    h: "C/C++", hpp: "C/C++", r: "R", m: "MATLAB", tex: "LaTeX", md: "Docs",
    yml: "Config", yaml: "Config", json: "Config", toml: "Config", csv: "Data",
    tsv: "Data", parquet: "Data", npy: "Data", npz: "Data", xlsx: "Data", h5: "Data"
  };
  const DATA_EXT = ["csv", "tsv", "parquet", "npy", "npz", "xlsx", "xls", "h5", "hdf5", "pkl", "jsonl"];
  const LOCK_NAMES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "uv.lock", "cargo.lock", "go.sum"];

  function fmtBytes(n) {
    if (!n || n < 1024) return (n || 0) + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
    return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
  }

  function fileExt(name) {
    const parts = String(name).toLowerCase().split(".");
    return parts.length > 1 ? parts.pop() : "";
  }

  function gapItem(title, detail, priority) {
    return { title: title, detail: detail, priority: priority || "中" };
  }

  function candidatesFor(gaps) {
    const map = {
      tests: ["补齐核心模块测试与评测口径", "把核心路径变成可重复的测试/评估入口，先证明改动没有破坏已有行为。", "核心路径通过率 / 覆盖率"],
      lock: ["补一键复现入口与锁文件", "固定依赖与环境，让另一台机器也能复现当前结果。", "复现检查通过率"],
      readme: ["补齐运行入口与研究说明", "外部读者需要知道数据从哪来、脚本怎么跑、结果如何核对。", "文档完备度"],
      license: ["补齐许可证与数据使用边界", "明确代码、数据和外部资源的使用条件，避免投稿/开源时的合规风险。", "合规检查通过率"],
      ci: ["把测试与复现检查接入 CI", "让每次改动自动回答：核心路径是否仍然可运行。", "CI 通过率"],
      data: ["把 notebook 数据流整理成可复现实验入口", "冻结数据切分、随机种子与运行环境，避免结果依赖本地状态。", "数据/入口完整性"],
      eval: ["预注册评测口径与对照矩阵", "先写清楚主指标、基线、停止条件和消融矩阵，再跑改进实验。", "对照完备度"],
      tree: ["读取仓库文件树后再定研究问题", "公开 API 只给元数据；需要本地 runtime 扫描测试、数据与入口。", "intake 完整度"]
    };
    const out = [];
    gaps.forEach(function (g) {
      const title = g.title;
      const key = title.indexOf("测试") >= 0 ? "tests"
        : (title.indexOf("锁") >= 0 || title.indexOf("环境") >= 0) ? "lock"
        : title.indexOf("说明") >= 0 ? "readme"
        : title.indexOf("许可") >= 0 ? "license"
        : title.indexOf("CI") >= 0 ? "ci"
        : title.indexOf("数据") >= 0 ? "data"
        : title.indexOf("文件树") >= 0 ? "tree" : "eval";
      const v = map[key] || map.eval;
      if (!out.some(function (x) { return x.title === v[0]; })) out.push({ title: v[0], why: v[1], metric: v[2] });
    });
    if (!out.length) out.push({ title: "从结构缺口生成一个可证伪的改进假设", why: "仓库结构较完整；下一步应把“改进”写成可测量、可否证的假设。", metric: "证据闭合度" });
    if (out.length < 3) out.push({ title: "先做一次基线复现与失败归档", why: "没有基线和失败记录，改进效果无法归因。", metric: "基线复现通过率" });
    if (out.length < 3) out.push({ title: "把结论写成可签署的证据包", why: "把 claim、run/EA、句槽与限制放在一起，才能对外交付。", metric: "导出阻断项" });
    return out.slice(0, 4);
  }

  function scanFolder(files) {
    const list = Array.from(files || []);
    if (!list.length) return null;
    let bytes = 0;
    const extCount = {};
    const dirs = new Set();
    const has = { readme: false, tests: false, notebooks: false, data: false, license: false, ci: false, lock: false };
    let root = "本地项目";
    list.forEach(function (f, index) {
      const path = f.webkitRelativePath || f.name;
      const low = path.toLowerCase();
      const ext = fileExt(path);
      const base = path.split("/").pop() || "";
      bytes += f.size || 0;
      extCount[ext] = (extCount[ext] || 0) + 1;
      if (index === 0) root = path.split("/")[0] || root;
      const first = path.split("/")[0];
      if (first && first !== path) dirs.add(first);
      if (/^readme(\.|$)/i.test(base)) has.readme = true;
      if (/^license|^copying/i.test(base)) has.license = true;
      if (low.indexOf("/.github/workflows/") >= 0 || low.indexOf("/.gitlab-ci") >= 0 || low.indexOf("azure-pipelines") >= 0) has.ci = true;
      if (low.indexOf("/tests/") >= 0 || low.indexOf("/test/") >= 0 || /(^|\/)(test_|.*\.(test|spec)\.)/.test(low)) has.tests = true;
      if (ext === "ipynb") has.notebooks = true;
      if (DATA_EXT.indexOf(ext) >= 0) has.data = true;
      if (LOCK_NAMES.indexOf(base.toLowerCase()) >= 0) has.lock = true;
    });
    const gaps = [];
    if (!has.tests) gaps.push(gapItem("缺少测试入口", "没有检测到 tests/ 或 test/spec 文件；核心路径无法自动验证。", "高"));
    if (!has.lock) gaps.push(gapItem("缺少环境锁", "依赖可能随机器漂移；复现检查会不稳定。", "高"));
    if (!has.readme) gaps.push(gapItem("缺少 README / 运行说明", "外部读者无法从仓库直接找到运行入口。", "中"));
    if (!has.license) gaps.push(gapItem("缺少许可证", "代码与数据的使用边界不清。", "中"));
    if (!has.ci) gaps.push(gapItem("缺少 CI", "测试与复现检查无法在每次改动后自动执行。", "中"));
    if (has.notebooks && !has.data) gaps.push(gapItem("Notebook 缺少数据快照", "notebook 引用的数据没有进入仓库或版本记录。", "中"));
    if (has.data && !has.notebooks) gaps.push(gapItem("数据存在但无可执行入口", "数据与运行脚本分离，读者不知道如何产生结果。", "中"));
    if (!gaps.length) gaps.push(gapItem("缺少预注册评测协议", "结构完整，但没有看到固定的主指标、基线、停止条件与对照矩阵。", "中"));
    const languages = Object.keys(extCount)
      .filter(function (e) { return extCount[e] > 0; })
      .map(function (e) { return { name: EXT_LANG[e] || (e ? "." + e : "其他"), count: extCount[e] }; })
      .sort(function (a, b) { return b.count - a.count; })
      .slice(0, 4);
    const score = Math.max(18, Math.min(98, 100 - gaps.length * 10 - (has.tests ? 0 : 6)));
    return {
      name: root, source: "本地文件夹 · 只读", files: list.length, bytes: bytes,
      languages: languages, dirs: Array.from(dirs).slice(0, 6), has: has, gaps: gaps,
      candidates: candidatesFor(gaps), score: score,
      note: "只读取文件名与大小；未读取文件内容、未上传、未执行代码。"
    };
  }

  function sampleProfile() {
    const has = { readme: true, tests: true, notebooks: true, data: true, license: true, ci: true, lock: false };
    const gaps = [
      gapItem("缺少环境锁", "示例仓库有依赖清单，但没有 lock file；换机器后复现可能漂移。", "高"),
      gapItem("缺少预注册评测协议", "没有冻结主指标、数据切分与停止条件；结果难以归因。", "中")
    ];
    return {
      name: "demo-lab/evidence-runner", source: "示例仓库 · SIM", files: 128, bytes: 4404019,
      languages: [{ name: "Python", count: 74 }, { name: "TypeScript", count: 31 }, { name: "Docs", count: 23 }],
      dirs: ["src", "tests", "notebooks", "data", ".github"], has: has, gaps: gaps,
      candidates: candidatesFor(gaps), score: 74,
      note: "示例 profile，用于展示 intake 流程；不是实际扫描结果。"
    };
  }

  function renderIntake(profile) {
    if (!intakeReport) return;
    if (!profile) {
      intakeReport.classList.remove("is-filled", "ir-cascade");
      intakeReport.innerHTML = '<div class="intake-preview" id="intake-preview">' +
        '<div class="ip-head"><span class="panel-kicker">REPORT PREVIEW</span><span class="badge sim">AWAITING SOURCE</span></div>' +
        '<div class="ip-hero"><div><h3>体检会产出什么</h3><p>只读扫描文件名与结构，得到三类可核对信号；再由你决定是否带入研究运行。</p></div><div class="ip-score-ghost" aria-hidden="true"><span>—</span><small>READINESS</small></div></div>' +
        '<div class="ip-grid"><div class="ip-card"><span class="ip-k">01 / STRUCTURE</span><b>结构统计</b><ul><li>文件数 / 体积</li><li>语言与目录</li><li>notebook / 数据</li></ul><div class="ip-ghost" aria-hidden="true"><i style="--w:82%"></i><i style="--w:58%"></i><i style="--w:70%"></i></div></div>' +
        '<div class="ip-card"><span class="ip-k">02 / REPRODUCIBILITY</span><b>可复现性信号</b><ul><li>测试 / 环境锁</li><li>README / 许可证</li><li>CI / 数据入口</li></ul><div class="ip-ghost" aria-hidden="true"><i style="--w:44%"></i><i style="--w:74%"></i><i style="--w:52%"></i></div></div>' +
        '<div class="ip-card"><span class="ip-k">03 / DIRECTIONS</span><b>候选研究方向</b><ul><li>可证伪假设</li><li>主指标与基线</li><li>首个复现实验</li></ul><div class="ip-ghost" aria-hidden="true"><i style="--w:66%"></i><i style="--w:48%"></i><i style="--w:76%"></i></div></div></div>' +
        '<div class="ip-scanner" aria-hidden="true"><div class="ip-scan-copy"><span>WAITING FOR SOURCE</span><span>只读 · 不上传 · 不执行</span></div></div>' +
        '<div class="ip-foot"><span>体检结果不是效果结论；缺口只用于生成可检验的研究问题。</span><span>LOCAL / SIGNALS</span></div></div>';
      return;
    }
    const yesNo = function (v) { return v === true ? ["是", "ok"] : (v === false ? ["否", "miss"] : ["—", ""]); };
    const stat = function (label, value, cls) {
      return '<div class="ir-stat"><span>' + escapeHtml(label) + '</span><b class="' + (cls || "") + '"><i></i>' + escapeHtml(value) + '</b></div>';
    };
    const t = yesNo(profile.has.tests), n = yesNo(profile.has.notebooks), d = yesNo(profile.has.data), l = yesNo(profile.has.license), c = yesNo(profile.has.ci);
    const langText = profile.languages.map(function (x) { return x.name + " " + x.count; }).join(" / ") || "—";
    const gapsHtml = profile.gaps.map(function (g, i) {
      const high = g.priority === "高";
      return '<li class="ir-gap"><span class="' + (high ? "" : "mid") + '">' + String(i + 1).padStart(2, "0") + '</span><div><b>' + escapeHtml(g.title) + '</b><p>' + escapeHtml(g.detail) + '</p></div><em class="' + (high ? "" : "mid") + '">' + escapeHtml(g.priority || "中") + '</em></li>';
    }).join("");
    const candHtml = profile.candidates.map(function (x, i) {
      return '<button type="button" class="ir-cand" data-cand-index="' + i + '" aria-label="把候选方向“' + escapeHtml(x.title) + '”设为研究目标"><span>' + String(i + 1).padStart(2, "0") + '</span><div><b>' + escapeHtml(x.title) + '</b><p>' + escapeHtml(x.why) + '</p><em>' + escapeHtml(x.metric) + '</em><i class="pick-hint">已设为目标</i></div></button>';
    }).join("");
    const scoreHtml = profile.score == null
      ? '<div class="ir-score is-empty" style="--v:0"><b>—</b><small>READINESS</small></div>'
      : '<div class="ir-score" id="ir-score" style="--v:0"><b id="ir-score-value">0</b><small>READINESS</small></div>';
    intakeReport.classList.remove("ir-cascade");
    intakeReport.classList.add("is-filled");
    intakeReport.innerHTML =
      '<div class="ir-head"><div class="ir-id"><div class="ir-source"><i></i>' + escapeHtml(profile.source) + '<span>· READ ONLY</span></div><h3>' + escapeHtml(profile.name) + '</h3><p>' + escapeHtml(profile.note) + '</p></div>' + scoreHtml + '</div>' +
      '<div class="ir-discipline"><span><i>✓</i>只读文件名与大小</span><span><i>✓</i>不上传文件</span><span><i>✓</i>不执行代码</span><span><i>i</i>READINESS 仅表示结构就绪度，不是质量或效果评分</span></div>' +
      '<div class="ir-stats">' +
        stat("files", profile.files == null ? "—" : String(profile.files)) +
        stat("size", profile.bytes == null ? "—" : fmtBytes(profile.bytes)) +
        stat("languages", langText) +
        stat("tests", t[0], t[1]) +
        stat("notebooks", n[0], n[1]) +
        stat("data", d[0], d[1]) +
        stat("license", l[0], l[1]) +
        stat("ci", c[0], c[1]) +
      '</div>' +
      '<div class="ir-section-head"><span>GAPS / 可研究缺口</span><em>' + profile.gaps.length + ' items</em></div><ul class="ir-gaps">' + gapsHtml + '</ul>' +
      '<div class="ir-section-head"><span>AUTO RESEARCH / 候选方向</span><em>点击候选，写入目标</em></div><div class="ir-cands">' + candHtml + '</div>' +
      '<div class="ir-actions"><button class="btn btn-primary" type="button" data-start-research><span>开始 Auto Research</span><span aria-hidden="true">→</span></button><button class="ir-reset" type="button" data-reset-report>重新体检</button><span class="fineprint">候选方向是结构启发式，不是已验证假设；仓库场景为 SIM，真实克隆 / 运行需要本地 runtime。</span></div>';
    requestAnimationFrame(function () {
      intakeReport.classList.add("ir-cascade");
      const ring = $("#ir-score");
      if (ring && profile.score != null) {
        requestAnimationFrame(function () {
          ring.style.setProperty("--v", profile.score);
          countUp($("#ir-score-value"), profile.score, 780);
        });
      }
    });
    setIntakeFlow(3);
  }

  async function readRepoUrl(url) {
    const match = String(url || "").match(/github\.com\/([^/]+)\/([^/#?]+)/i);
    if (!match) throw new Error("目前只支持公开 GitHub 仓库 URL");
    const controller = new AbortController();
    const timeout = setTimeout(function () { controller.abort(); }, 12000);
    let res;
    try {
      res = await fetch("https://api.github.com/repos/" + encodeURIComponent(match[1]) + "/" + encodeURIComponent(match[2]), { headers: { Accept: "application/vnd.github+json" }, signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
    if (!res.ok) throw new Error("GitHub HTTP " + res.status);
    const data = await res.json();
    const has = { readme: !!data.description, tests: null, notebooks: null, data: null, license: !!(data.license && data.license.spdx_id), ci: null, lock: null };
    const gaps = [];
    if (!has.license) gaps.push(gapItem("缺少许可证", "公开仓库没有声明许可证，代码/数据的使用边界不清。", "中"));
    if (!data.description) gaps.push(gapItem("缺少项目说明", "仓库没有 description，外部读者难以判断研究意图。", "低"));
    gaps.push(gapItem("未读取文件树", "GitHub API 只返回元数据；测试、数据和复现入口需要本地 runtime 扫描。", "中"));
    return {
      name: data.full_name || (match[1] + "/" + match[2]), source: "GitHub API · 公开元数据",
      files: null, bytes: data.size ? data.size * 1024 : null,
      languages: data.language ? [{ name: data.language, count: 1 }] : [],
      dirs: [], has: has, gaps: gaps, candidates: candidatesFor(gaps), score: null,
      note: "只读取公开元数据：stars " + (data.stargazers_count || 0) + " · forks " + (data.forks_count || 0) + "；未克隆、未读取文件树、未执行代码。"
    };
  }

  function urlFallback(url) {
    const name = String(url || "公开仓库").replace(/^https?:\/\//, "").replace(/\/$/, "");
    const gaps = [gapItem("未读取公开元数据", "浏览器无法读取该仓库；可能是不存在、私有或网络受限。", "中")];
    return {
      name: name, source: "URL 登记 · 未读取", files: null, bytes: null, languages: [], dirs: [],
      has: { tests: null, notebooks: null, data: null, license: null, ci: null }, gaps: gaps,
      candidates: candidatesFor(gaps), score: null,
      note: "仅登记 URL；没有克隆或执行。Auto Research 只能生成通用计划。"
    };
  }

  function setIntakeStatus(text, tone) {
    if (!intakeStatus) return;
    intakeStatus.className = "status-line" + (tone ? " is-" + tone : "");
    intakeStatus.innerHTML = '<i class="dot ' + (tone === "ok" ? "dot-live" : tone === "warn" ? "dot-warn" : "dot-sim") + '"></i><span>' + escapeHtml(text) + '</span>';
  }

  function setIntakeMode(mode) {
    intakeMode = mode;
    $$(".intake-tab").forEach(function (b) {
      const on = b.getAttribute("data-intake-mode") === mode;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", String(on));
    });
    $$("[data-intake-pane]").forEach(function (p) { p.hidden = p.getAttribute("data-intake-pane") !== mode; });
    if (mode === "url" && repoUrlInput) setTimeout(function () { repoUrlInput.focus(); }, 30);
  }

  async function presentProfile(profile) {
    if (!profile || !intakeReport) return;
    const token = ++intakeScanToken;
    setIntakeBusy(true);
    setIntakeFlow(2);
    intakeReport.classList.remove("is-filled", "ir-cascade");
    intakeReport.innerHTML = scanningShell(profile.name, profile.note);
    setScanProgress(0);
    await sleep(300);
    if (token !== intakeScanToken) return;
    setScanProgress(1);
    await sleep(340);
    if (token !== intakeScanToken) return;
    setScanProgress(2);
    await sleep(300);
    if (token !== intakeScanToken) return;
    renderIntake(profile);
    intakeProfile = profile;
    setIntakeBusy(false);
    const countText = profile.files == null ? "公开元数据" : profile.files + " 个文件";
    setIntakeStatus("体检完成：" + countText + " · " + profile.gaps.length + " 项缺口；未上传内容、未执行代码。", "ok");
  }

  async function presentUrl(url) {
    const token = ++intakeScanToken;
    setIntakeBusy(true);
    setIntakeFlow(2);
    intakeReport.classList.remove("is-filled", "ir-cascade");
    intakeReport.innerHTML = scanningShell(url, "GitHub 公开元数据 · 不克隆、不读取文件树");
    setScanProgress(0);
    stagedProfile = null;
    let profile = null;
    let error = null;
    try {
      profile = await readRepoUrl(url);
    } catch (err) {
      error = err && err.name === "AbortError" ? new Error("请求超时") : err;
      profile = urlFallback(url);
    }
    if (token !== intakeScanToken) return;
    setScanProgress(1);
    await sleep(300);
    if (token !== intakeScanToken) return;
    setScanProgress(2);
    await sleep(300);
    if (token !== intakeScanToken) return;
    renderIntake(profile);
    intakeProfile = profile;
    setIntakeBusy(false);
    setIntakeStatus(
      error ? "元数据读取失败：" + error.message + "；已登记 URL，可继续生成通用计划。" : "已读取公开元数据；未克隆、未读取文件树。",
      error ? "warn" : "ok"
    );
  }

  async function runIntakeScan() {
    if (intakeScanBusy) return;
    if (intakeMode === "folder") {
      if (folderInput && folderInput.files && folderInput.files.length) {
        stagedProfile = scanFolder(folderInput.files);
        if (stagedProfile) { presentProfile(stagedProfile); return; }
      }
      if (stagedProfile) { presentProfile(stagedProfile); return; }
      setIntakeStatus("请先选择一个本地项目文件夹，或载入示例。", "warn");
      return;
    }
    const url = repoUrlInput ? repoUrlInput.value.trim() : "";
    if (!url) { setIntakeStatus("请输入公开仓库 URL。", "warn"); return; }
    presentUrl(url);
  }

  function pickCandidate(index) {
    if (!intakeProfile) return;
    const c = intakeProfile.candidates[index];
    if (!c) return;
    const goal = (c.title + "：" + c.why).slice(0, 160);
    if (goalInput) {
      goalInput.value = goal;
      syncGoalCount();
    }
    $$(".ir-cand", intakeReport).forEach(function (btn, i) { btn.classList.toggle("is-picked", i === index); });
    setIntakeStatus("已把候选 " + String(index + 1).padStart(2, "0") + " 写为目标；可继续修改，再进入研究运行。", "ok");
  }

  function resetIntakeReport() {
    intakeScanToken++;
    intakeProfile = null;
    stagedProfile = folderInput && folderInput.files && folderInput.files.length ? scanFolder(folderInput.files) : null;
    renderIntake(null);
    setIntakeFlow(stagedProfile ? 1 : 0);
    setIntakeBusy(false);
    setIntakeStatus(stagedProfile ? "已选择 " + stagedProfile.name + "；点击开始体检重新生成报告。" : "已清空报告；选择来源后开始体检。");
  }

  function startRepoResearch() {
    if (!intakeProfile) { setIntakeStatus("先做一次体检，再开始 Auto Research。"); return; }
    const goal = (goalInput && goalInput.value.trim()) || "从仓库结构缺口生成可证伪的改进假设";
    demoProjectQuery = "scenario=repo&project=" + encodeURIComponent(intakeProfile.name) + "&goal=" + encodeURIComponent(goal);
    showAppView("demo", "console");
    switchDemoMode("console", true);
    if (appViewTitle) appViewTitle.textContent = "演示台 · " + intakeProfile.name;
    setIntakeStatus("已带入「" + intakeProfile.name + "」；研究运行使用 SIM 仓库场景。");
  }

  $$(".intake-tab").forEach(function (btn) { btn.addEventListener("click", function () { setIntakeMode(btn.getAttribute("data-intake-mode")); }); });
  const pickFolder = $("#pick-folder");
  if (pickFolder && folderInput) pickFolder.addEventListener("click", function () { folderInput.click(); });
  if (folderInput) folderInput.addEventListener("change", function () {
    if (!folderInput.files.length) return;
    const p = scanFolder(folderInput.files);
    if (!p) return;
    stagedProfile = p;
    if (folderNote) {
      folderNote.innerHTML = '<i></i>' + escapeHtml(p.name) + " · " + p.files + " files";
      folderNote.classList.add("is-ready");
    }
    setIntakeFlow(1);
    setIntakeStatus("已选择 " + p.name + " · " + p.files + " 个文件；正在生成只读体检。", "ok");
    presentProfile(p);
  });
  const loadSample = $("#load-sample");
  if (loadSample) loadSample.addEventListener("click", function () {
    stagedProfile = sampleProfile();
    if (folderNote) {
      folderNote.innerHTML = '<i></i>示例 profile · SIM';
      folderNote.classList.add("is-ready");
    }
    setIntakeFlow(1);
    setIntakeStatus("已载入示例仓库 profile（SIM）；正在生成只读体检。", "ok");
    presentProfile(stagedProfile);
  });
  if (intakeScanBtn) intakeScanBtn.addEventListener("click", runIntakeScan);
  if (readUrlBtn) readUrlBtn.addEventListener("click", function () { setIntakeMode("url"); runIntakeScan(); });
  function clearCandidatePick() {
    $$(".ir-cand", intakeReport).forEach(function (btn) { btn.classList.remove("is-picked"); });
  }
  $$("[data-goal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (goalInput) {
        goalInput.value = btn.getAttribute("data-goal");
        syncGoalCount();
        clearCandidatePick();
      }
    });
  });
  if (goalInput) goalInput.addEventListener("input", function () {
    syncGoalCount();
    clearCandidatePick();
  });
  if (repoUrlInput) repoUrlInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      runIntakeScan();
    }
  });
  if (intakeReport) intakeReport.addEventListener("click", function (event) {
    const cand = event.target.closest("[data-cand-index]");
    if (cand) { pickCandidate(Number(cand.getAttribute("data-cand-index"))); return; }
    if (event.target.closest("[data-reset-report]")) { resetIntakeReport(); return; }
    if (event.target.closest("[data-start-research]")) startRepoResearch();
  });
  syncGoalCount();
  setIntakeFlow(0);

  /* ---------------- demo studio ---------------- */
  const demoFrame = $("#demo-iframe");
  const frameLoading = $("#frame-loading");
  const demoSection = $("#demo");
  let frameLoadingTimer = null;
  function showFrameLoading() {
    if (!frameLoading) return;
    clearTimeout(frameLoadingTimer);
    frameLoading.classList.add("is-on");
    frameLoadingTimer = setTimeout(hideFrameLoading, 2600);
  }
  function hideFrameLoading() {
    clearTimeout(frameLoadingTimer);
    if (frameLoading) frameLoading.classList.remove("is-on");
  }
  const demoLenses = $$(".demo-lens");
  const workbenchJumps = $$(".wb-jump");
  const demoSubbar = $("#workbench-subbar");
  const demoModeMeta = $("#demo-mode-meta");
  const demoFrameLabel = $("#demo-frame-label");
  const demoNote = $("#demo-note");
  const studioHead = $("#studio-head");
  const studioTitle = $("#studio-title");
  const studioTitleEn = $("#studio-title-en");
  const studioLede = $("#studio-lede");
  const studioFacts = $("#studio-facts");
  const studioStateLabel = $("#studio-state-label");
  const demoStudio = $("#demo-studio");
  let demoMode = "console";
  let demoProjectQuery = "";
  let currentWorkbenchView = "manuscript";
  let consoleAutoplayed = false;
  let demoBodyObserver = null;

  const DEMO_META = {
    console: {
      meta: "SIM · 4 场景 · 9 阶段 · 自动播放一次",
      label: "research-agent / console · embed",
      note: "研究运行在进入视口后自动播放一次 SIM 流程；每阶段按子步骤逐步展开对象流、阶段卡、指令与日志，未到的内容保持淡出。",
      hash: "console"
    },
    workbench: {
      meta: "SIM · 7 视图 · 体检 / 变更 / 签署",
      label: "research-agent / workbench · embed",
      note: "7 个视图可切换；点来源、句子或债务，右侧检查器回答“这句话凭什么存在”。全部为 SIM。",
      hash: "workbench"
    },
    evolution: {
      meta: "SIM · EV1–EV4 · 租约 · 过程反馈",
      label: "research-agent / evolution · embed",
      note: "候选改进先过 EV1–EV4 四问，再发有期限的租约；撤销后依赖的运行与稿句一起复核。全部为 SIM 设计演示。",
      hash: "evolution"
    }
  };

  const STUDIO_META = {
    console: {
      title: "研究运行",
      en: "RUN CONSOLE",
      lede: "逐阶段展开的一次可检查运行：对象流、指令流、失败分支与阶段契约共用同一套证据对象。",
      facts: [["9", "阶段"], ["4", "硬不变量"], ["SIM", "非实测"]],
      state: "AUTO PLAY · SIM"
    },
    workbench: {
      title: "证据工作台",
      en: "EVIDENCE WORKBENCH",
      lede: "七个视图追踪同一份证据对象：来源、句子、债务与签署。右侧检查器回答“凭什么存在”。",
      facts: [["7", "视图"], ["1", "证据图"], ["SIM", "非实测"]],
      state: "INSPECT · SIM"
    },
    evolution: {
      title: "自进化",
      en: "SELF-EVOLUTION",
      lede: "候选改进先过 EV1–EV4，再发有期限的租约；撤销后依赖的运行与稿句一起复核。",
      facts: [["4", "问题"], ["1", "租约"], ["SIM", "设计演示"]],
      state: "CANDIDATE · SIM"
    }
  };

  function applyStudioInfo(mode) {
    const info = STUDIO_META[mode] || STUDIO_META.console;
    if (studioTitle) studioTitle.textContent = info.title;
    if (studioTitleEn) studioTitleEn.textContent = info.en;
    if (studioLede) studioLede.textContent = info.lede;
    if (studioFacts) {
      const factTitles = {
        "阶段": "P0–P8 为叙事压缩，逐阶段契约见 STAGE CONTRACT",
        "硬不变量": "claim←Evidence；export←Closure；Run 钉模板；技能租约可撤销",
        "非实测": "所有 RUN 数据与状态为 SIM，不代表真实效果"
      };
      studioFacts.innerHTML = info.facts.map(function (f) {
        return '<span title="' + escapeHtml(factTitles[f[1]] || "") + '"><b>' + escapeHtml(f[0]) + "</b>" + escapeHtml(f[1]) + "</span>";
      }).join("");
    }
    if (studioStateLabel) studioStateLabel.textContent = info.state;
    if (studioHead) {
      studioHead.setAttribute("data-mode", mode);
      studioHead.classList.remove("is-switching");
      void studioHead.offsetWidth;
      studioHead.classList.add("is-switching");
      studioHead.classList.add("is-live");
    }
    if (demoStudio) demoStudio.setAttribute("data-mode", mode);
  }

  function fitDemoFrame() {
    if (!demoFrame) return;
    try {
      const doc = demoFrame.contentDocument;
      if (!doc || !doc.body) return;
      const max = demoMode === "evolution"
        ? 2800
        : (demoMode === "console"
          ? (window.innerWidth <= 680 ? 1800 : 1600)
          : (window.innerWidth <= 680 ? 1400 : 1100));
      const height = Math.min(max, Math.max(620, doc.body.scrollHeight + 2));
      demoFrame.style.height = height + "px";
    } catch (error) {}
  }

  function observeDemoBody() {
    if (demoBodyObserver) {
      try { demoBodyObserver.disconnect(); } catch (error) {}
      demoBodyObserver = null;
    }
    if (!demoFrame || !("ResizeObserver" in window)) return;
    try {
      const body = demoFrame.contentDocument && demoFrame.contentDocument.body;
      if (!body) return;
      demoBodyObserver = new ResizeObserver(function () { fitDemoFrame(); });
      demoBodyObserver.observe(body);
    } catch (error) {}
  }

  function applyWorkbenchView(view) {
    if (!demoFrame) return;
    try {
      const doc = demoFrame.contentDocument;
      if (!doc) return false;
      const tab = doc.querySelector('.wb-tab[data-wb-view="' + view + '"]');
      if (!tab) return false;
      tab.click();
      setTimeout(fitDemoFrame, 120);
      return true;
    } catch (error) {
      return false;
    }
  }

  function maybeAutoplayConsole() {
    if (demoMode !== "console" || consoleAutoplayed || !demoFrame || !demoSection) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = demoSection.getBoundingClientRect();
    if (rect.top > window.innerHeight * 0.72 || rect.bottom < 80) return;
    try {
      const doc = demoFrame.contentDocument;
      const button = doc && doc.getElementById("run-toggle");
      if (!button || button.disabled) return;
      consoleAutoplayed = true;
      setTimeout(() => { try { button.click(); } catch (error) {} }, 650);
    } catch (error) {}
  }

  function switchDemoMode(mode, force) {
    if (!demoFrame) return;
    applyStudioInfo(mode);
    if (mode === demoMode && !force) return;
    demoMode = mode;
    consoleAutoplayed = false;
    showFrameLoading();
    demoLenses.forEach((button) => button.classList.toggle("is-active", button.getAttribute("data-demo-mode") === mode));
    if (demoSubbar) demoSubbar.hidden = mode !== "workbench";
    const info = DEMO_META[mode];
    if (demoModeMeta) demoModeMeta.textContent = info.meta;
    if (demoFrameLabel) demoFrameLabel.textContent = info.label;
    if (demoNote) demoNote.textContent = info.note;
    const suffix = demoProjectQuery ? "?" + demoProjectQuery : "";
    if (appFullLink) appFullLink.href = "./demo/" + suffix + "#" + info.hash;
    demoFrame.src = "./demo/index.html?embed=" + mode + (demoProjectQuery ? "&" + demoProjectQuery : "");
  }

  if (demoFrame) {
    demoFrame.addEventListener("load", () => {
      hideFrameLoading();
      fitDemoFrame();
      observeDemoBody();
      if (document.body.classList.contains("present")) setTimeout(function () { postDemoFocus(true); }, 80);
      if (demoMode === "workbench") applyWorkbenchView(currentWorkbenchView);
      if (demoMode === "console") maybeAutoplayConsole();
    });
    setTimeout(hideFrameLoading, 1600);
    window.addEventListener("resize", fitDemoFrame);
    if ("IntersectionObserver" in window && demoSection) {
      const demoObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => { if (entry.isIntersecting) maybeAutoplayConsole(); });
      }, { threshold: 0.25 });
      demoObserver.observe(demoSection);
    }
  }

  demoLenses.forEach((button) => {
    button.addEventListener("click", () => switchDemoMode(button.getAttribute("data-demo-mode")));
  });
  workbenchJumps.forEach((button) => {
    button.addEventListener("click", () => {
      workbenchJumps.forEach((b) => b.classList.remove("is-active"));
      button.classList.add("is-active");
      currentWorkbenchView = button.getAttribute("data-embed-view");
      if (demoMode === "workbench") applyWorkbenchView(currentWorkbenchView);
    });
  });

  /* ---------------- misc ---------------- */
  document.querySelectorAll('a[href^="#"]:not([data-view])').forEach((link) => {
    link.addEventListener("click", (event) => {
      const target = document.querySelector(link.getAttribute("href"));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  initDigest();
  applyStudioInfo("console");

  const bootCover = $("#boot-cover");
  const reduceBoot = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceBoot) {
    document.body.classList.add("ready");
    if (bootCover) bootCover.remove();
  } else {
    setTimeout(function () { document.body.classList.add("ready"); }, 1050);
    setTimeout(function () { if (bootCover && bootCover.parentNode) bootCover.remove(); }, 2100);
  }

  console.info("[Research Agent] site ready · LIVE PUBLIC retrieval uses OpenAlex; demo/case/skill states are SIM.");
})();
