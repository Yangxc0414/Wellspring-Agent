#!/usr/bin/env node
/**
 * Task readiness check for the static workbench demo.
 *
 * Answers one question repeatably: can every session in the sidebar actually be
 * walked through in front of an audience? It clicks each task and asserts the
 * things a viewer would notice:
 *
 *   - the session has a real transcript (messages + at least one card);
 *   - nothing 404s and no JS error fires;
 *   - the thread's "回放 N/9" equals the RUN panel's "N/9 stages";
 *   - a task with a run record does not show "not run / not sealed" in EVIDENCE;
 *   - the teaching panel says it is a generic template on non-full-chain tasks.
 *
 * Usage (after `npm run build:site`):
 *   node scripts/check_task_readiness.mjs
 *
 * Exits 1 on any failure so it can gate a release step. Read-only: it serves
 * site/ from a temporary localhost port and never writes.
 */
import { chromium } from "../apps/web/node_modules/playwright/index.mjs";
import http from "http";
import fs from "fs";
import path from "path";

const ROOT = path.resolve("site");
const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2"
};

function serve() {
  return http.createServer((req, res) => {
    let rel = decodeURIComponent(req.url.split("?")[0]);
    let file = path.join(ROOT, rel);
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(file)] || "application/octet-stream",
      "Cache-Control": "no-store"
    });
    fs.createReadStream(file).pipe(res);
  });
}

const failures = [];
const rows = [];

function fail(task, message) {
  failures.push(`${task}: ${message}`);
}

async function openPanel(page, label) {
  const buttons = page.locator(".context-tabs button");
  for (let i = 0; i < (await buttons.count()); i++) {
    if ((await buttons.nth(i).innerText()).trim() === label) {
      await buttons.nth(i).click({ force: true });
      await page.waitForTimeout(200);
      return true;
    }
  }
  return false;
}

const server = serve();
server.listen(0, "127.0.0.1", async () => {
  const port = server.address().port;
  let launch = { headless: true };
  for (const channel of ["chrome", "msedge"]) {
    try {
      const probe = await chromium.launch({ ...launch, channel });
      await probe.close();
      launch.channel = channel;
      break;
    } catch {
      /* try the next installed browser */
    }
  }

  const browser = await chromium.launch(launch);
  const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
  const problems = [];
  page.on("pageerror", (e) => problems.push(`JS ${e.message.slice(0, 100)}`));
  page.on("response", (r) => {
    if (r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.url().split("/").slice(-1)[0]}`);
  });

  await page.goto(`http://127.0.0.1:${port}/app/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  const tasks = page.locator(".task-row");
  const count = await tasks.count();
  if (!count) fail("workspace", "no task rows found - is site/app built?");

  for (let i = 0; i < count; i++) {
    await tasks.nth(i).click();
    await page.waitForTimeout(320);
    const title = (await tasks.nth(i).locator(".task-row-title").innerText().catch(() => "?")).trim();
    const status = (await tasks.nth(i).locator(".task-row-time").innerText().catch(() => "")).trim();
    const messages = await page.locator(".message").count();
    const cards = await page.locator(".artifact").count();
    const chars = (await page.locator(".thread-inner").innerText().catch(() => "")).replace(/\s+/g, " ").length;
    const chips = await page.locator(".chip").allInnerTexts().catch(() => []);
    const threadChip = chips.find((c) => /stages/.test(c)) ?? "";
    const threadDone = Number((threadChip.match(/(\d+)\/9/) ?? [])[1]);

    if (messages < 3) fail(title, `only ${messages} messages`);
    if (cards < 1) fail(title, "no artifact card");
    if (chars < 400) fail(title, `transcript too thin (${chars} chars)`);

    await openPanel(page, "RUN");
    const runRow = (await page.locator(".run-state-row").innerText().catch(() => "")).replace(/\n/g, " ");
    const runDone = Number((runRow.match(/(\d+)\/9/) ?? [])[1]);
    if (Number.isFinite(threadDone) && Number.isFinite(runDone) && threadDone !== runDone) {
      fail(title, `stage counts disagree: thread ${threadDone}/9 vs RUN ${runDone}/9`);
    }

    await openPanel(page, "EVIDENCE");
    const chain = (await page.locator(".chain").innerText().catch(() => "")).replace(/\s+/g, " ");
    const threadText = await page.locator(".thread-inner").innerText().catch(() => "");
    const hasRunRecord = !/运行记录\s*not run/.test(chain);
    // Require evidence of an actual artifact, not advice to create one: a task
    // with no run legitimately says "先跑出 RunCapsule / EA", which is a next
    // step, not a claim that the capsule exists.
    const citesArtifact =
      /EA-[0-9a-f]{6,}/.test(threadText) || /RunCapsule[^\n]{0,12}(✓|completed|完成)/.test(threadText);
    if (citesArtifact && !hasRunRecord) {
      fail(title, "transcript cites a capsule/EA but EVIDENCE says not run");
    }
    if (/证据制品\s*not sealed/.test(chain) && /EA-[0-9a-f]{6,}/.test(threadText)) {
      fail(title, "transcript cites an EA id but EVIDENCE says not sealed");
    }

    await openPanel(page, "演示流程");
    const banner = (await page.locator(".flow-banner").innerText().catch(() => "")).replace(/\s+/g, " ");
    if (title !== "完整闭环：从检索到自改进" && !/通用模板（非当前任务）/.test(banner)) {
      fail(title, "teaching panel does not declare it is a generic template");
    }

    rows.push({ title, status, messages, cards, chars, stages: runDone });
  }

  if (problems.length) fail("page", [...new Set(problems)].join(" | "));

  console.log("task readiness report");
  console.log("-".repeat(78));
  for (const r of rows) {
    console.log(
      `${r.title.padEnd(24, " ")} [${r.status}]  msgs=${String(r.messages).padStart(2)}  cards=${String(r.cards).padStart(2)}  chars=${String(r.chars).padStart(5)}  stages=${r.stages}/9`
    );
  }
  console.log("-".repeat(78));
  if (failures.length) {
    console.log(`FAILED (${failures.length})`);
    for (const f of failures) console.log("  - " + f);
  } else {
    console.log("OK - every session is demonstrable and internally consistent");
  }

  await browser.close();
  server.close();
  process.exit(failures.length ? 1 : 0);
});
