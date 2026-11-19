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

// FRESH context: what a first-time viewer / clean demo machine sees
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(`http://127.0.0.1:${port}/app/`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
console.log("=== 默认 tab ===");
const activeTab = await page.locator("[role=tab][aria-selected=true]").allTextContents();
console.log(JSON.stringify(activeTab));
console.log("=== 侧栏会话 ===");
const rows = await page.locator("button.task-row").evaluateAll((els) => els.map((e) => ({
  t: e.querySelector(".task-row-title")?.textContent?.trim(),
  s: e.querySelector(".task-row-time")?.textContent?.trim(),
  sel: e.className.includes("is-selected")
})));
rows.forEach((r) => console.log(`${r.sel ? ">" : " "} ${r.t} [${r.s}]`));
console.log("=== 顶部 kicker ===");
const kicker = await page.locator(".task-kicker").innerText().catch(()=>"(none)");
console.log(JSON.stringify(kicker));
console.log("=== 对话区滚动位置 ===");
const thread = await page.locator("#thread").evaluate((e)=>({top:e.scrollTop, h:e.scrollHeight, client:e.clientHeight}));
console.log(JSON.stringify(thread));
console.log("=== 对话第一条消息 ===");
const first = await page.locator(".thread-inner").innerText();
console.log(first.slice(0, 200));
await page.screenshot({ path: "runtime_data/demo-firstlook.png", fullPage: false });
await browser.close();
server.close();
