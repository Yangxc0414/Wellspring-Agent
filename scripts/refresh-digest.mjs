import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const queriesPath = path.join(root, "site", "data", "queries.json");
const outputPath = path.join(root, "site", "data", "digest.json");

function readQueries() {
  const queries = JSON.parse(fs.readFileSync(queriesPath, "utf8"));
  if (!Array.isArray(queries) || !queries.length) throw new Error("queries.json must be a non-empty array");
  return queries;
}

function reconstructAbstract(index) {
  if (!index || typeof index !== "object") return "";
  const pairs = [];
  for (const [word, positions] of Object.entries(index)) {
    if (!Array.isArray(positions)) continue;
    for (const position of positions) pairs.push([position, word]);
  }
  return pairs.sort((a, b) => a[0] - b[0]).map((pair) => pair[1]).join(" ").trim();
}

const RETRY_DELAYS_MS = [2000, 8000, 20000];

async function fetchQuery(item) {
  // OpenAlex 对匿名/数据中心来源限流（429）：mailto 进 polite pool + 退避重试。
  let lastError = null;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    if (attempt > 0) {
      console.error("retry:", item.id, "attempt", attempt, "after", RETRY_DELAYS_MS[attempt - 1], "ms");
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt - 1]));
    }
    try {
      return await fetchQueryOnce(item);
    } catch (error) {
      lastError = error;
      const retryable = /HTTP 429|HTTP 5\d\d|timeout|fetch failed|network/i.test(error.message);
      if (!retryable) throw error;
    }
  }
  throw lastError;
}

async function fetchQueryOnce(item) {
  const filters = ["title_and_abstract.search:" + item.query, "type:article"];
  if (Number(item.from_year) > 0) filters.push("from_publication_date:" + Number(item.from_year) + "-01-01");
  const params = [
    "filter=" + encodeURIComponent(filters.join(",")),
    "sort=" + encodeURIComponent("cited_by_count:desc"),
    "per-page=" + encodeURIComponent(String(item.limit || 6)),
    "select=" + encodeURIComponent("id,doi,title,publication_year,cited_by_count,authorships,primary_location,open_access,abstract_inverted_index")
  ];
  if (process.env.OPENALEX_MAILTO) params.push("mailto=" + encodeURIComponent(process.env.OPENALEX_MAILTO));
  const url = "https://api.openalex.org/works?" + params.join("&");
  const response = await fetch(url, {
    headers: { Accept: "application/json", "User-Agent": "ResearchWeave-digest/0.1" },
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error("OpenAlex HTTP " + response.status);
  const payload = await response.json();
  const works = (payload.results || []).map((work) => {
    const source = work.primary_location && work.primary_location.source;
    return {
      openalex_id: work.id || null,
      doi: work.doi || null,
      title: work.title || null,
      year: work.publication_year || null,
      cited_by: work.cited_by_count || 0,
      venue: (source && source.display_name) || null,
      authors: (work.authorships || []).slice(0, 3).map((a) => a.author && a.author.display_name).filter(Boolean),
      open_access: !!(work.open_access && work.open_access.is_oa),
      abstract: reconstructAbstract(work.abstract_inverted_index).slice(0, 600)
    };
  });
  return {
    id: item.id,
    label: item.label,
    query: item.query,
    from_year: item.from_year,
    total_hits: payload.meta && payload.meta.count ? payload.meta.count : null,
    returned: works.length,
    works
  };
}

const queries = readQueries();
const results = [];
const errors = [];

for (const item of queries) {
  try {
    results.push(await fetchQuery(item));
    console.log("ok:", item.id, results[results.length - 1].returned, "works");
  } catch (error) {
    errors.push({ id: item.id, message: error.message });
    console.error("fail:", item.id, error.message);
  }
}

if (!results.length) {
  // 全部查询失败（多为限流）：保留上一份 digest（页面标注 CACHED，数据本就不是
  // 证据级），大声记录 stale 并以 0 退出——cron 的限流抖动不该让仓库长期挂红；
  // 首次生成（无既有 digest）时仍然失败可见。
  if (fs.existsSync(outputPath)) {
    console.error("ALL queries failed (rate limited or network); keeping the previous digest (stale).");
    console.error("Will retry on the next scheduled run; consider setting OPENALEX_MAILTO for the polite pool.");
    process.exit(0);
  }
  console.error("no previous digest to keep and all queries failed");
  process.exit(1);
}

const digest = {
  generated_at: new Date().toISOString(),
  source: "OpenAlex /works",
  mode: "CACHED",
  license: "OpenAlex metadata; respect source licenses and attribution",
  queries: results,
  errors
};
fs.writeFileSync(outputPath, JSON.stringify(digest, null, 2) + "\n");
console.log("wrote", outputPath);
