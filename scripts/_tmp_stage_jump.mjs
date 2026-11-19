import { createRequire } from "module";
import http from "http";
import fs from "fs";
import path from "path";
const require = createRequire(new URL("../apps/web/node_modules/", import.meta.url));
const { chromium } = require("playwright");
const ROOT = path.resolve("site");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
const server = http.createServer((req, res) => {
  let rel = decodeURIComponent(req.url.split("?")[0]);
  if (rel === "/") rel = "/app/index.html";
  let file = path.join(ROOT, rel);
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!file.startsWith(ROOT) || !fs.existsSync(file)) { res.writeHead(404); res.end("nf"); return; }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
const launch = { headless: true };
for (const c of ["chrome", "msedge"]) { try { const b = await chromium.launch({ ...launch, channel: c }); await b.close(); launch.channel = c; break; } catch {} }
const browser = await chromium.launch(launch);
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(`http://127.0.0.1:${port}/app/`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);

console.log("默认任务:", (await page.locator(".task-head h1").innerText()).trim());
console.log("data-stage 消息数:", await page.locator("[data-stage]").count());
const stages = await page.locator("[data-stage]").evaluateAll((els) => els.map((e) => e.getAttribute("data-stage")));
console.log("已标注阶段:", JSON.stringify([...new Set(stages)]));

// click S4 flow node head (not the jump icon) -> should scroll + highlight
const s4head = page.locator(".flow-stage").filter({ has: page.locator(".flow-stage-id", { hasText: "S4" }) }).locator(".flow-stage-head").first();
console.log("S4 节点存在:", await s4head.count());
await s4head.click();
await page.waitForTimeout(500);
const target = page.locator('[data-stage="S4"]').first();
console.log("S4 目标消息高亮:", await target.evaluate((e) => e.className.includes("is-stage-focused")));
const inView = await target.evaluate((e) => {
  const r = e.getBoundingClientRect();
  return r.top >= 0 && r.bottom <= window.innerHeight;
});
console.log("S4 目标消息在视口内:", inView);

// click S5b jump icon -> should scroll + highlight
const s5bJump = page.locator(".flow-stage").filter({ has: page.locator(".flow-stage-id", { hasText: "S5b" }) }).locator(".flow-stage-jump").first();
await s5bJump.click();
await page.waitForTimeout(500);
const t5 = page.locator('[data-stage="S5b"]').first();
console.log("S5b 目标高亮:", await t5.evaluate((e) => e.className.includes("is-stage-focused")));

await page.screenshot({ path: "runtime_data/stage-jump-check.png", fullPage: false });
await browser.close();
server.close();
