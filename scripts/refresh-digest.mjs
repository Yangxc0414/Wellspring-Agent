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

async function fetchQuery(item) {
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
  console.error("no digest written: all queries failed");
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
