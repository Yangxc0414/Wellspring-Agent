// Real-DOM check for the workbench: renders the project closure inventory in a headless
// browser and prints what the page actually shows.
//
//   node scripts/web_page_check.mjs --url http://localhost:5199/ --project "idea to experiment"
//
// It exists because the in-app Browser exposes a zero-width viewport, so React's right-hand
// panel never lays out and innerText comes back empty. This script uses a real viewport and
// reports the panel text instead of assuming the data reached the page.
// playwright is installed under apps/web, and ESM resolution starts at this file's directory,
// so the dependency is required through that package root instead of the repo root.
import { createRequire } from "module";

const require = createRequire(new URL("../apps/web/node_modules/", import.meta.url));
const { chromium } = require("playwright");

const args = process.argv.slice(2);
const arg = (name, fallback = "") => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const url = arg("url", "http://localhost:5199/");
const projectHint = arg("project", "idea to experiment");
const launch = { headless: true };
for (const channel of ["chrome", "msedge"]) {
  try {
    const browser = await chromium.launch({ ...launch, channel });
    await browser.close();
    launch.channel = channel;
    break;
  } catch {
    /* try the next channel, then the bundled chromium */
  }
}

const browser = await chromium.launch(launch);
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(url, { waitUntil: "networkidle" });

const texts = () =>
  page.evaluate(() =>
    Array.from(document.querySelectorAll("button,[role=\"tab\"],summary"))
      .map((element) => (element.textContent || "").trim())
      .filter((text) => text && text.length <= 48)
  );

// Clicking through Playwright role locators is brittle here (labels are nested), so the
// clicks are dispatched on the element whose textContent matches, inside the page.
const clickText = (pattern, wide = false) =>
  page.evaluate(
    ({ source, broad }) => {
      const re = new RegExp(source, "i");
      // The PROJECTS tab is a real button, but the project chips inside it are plain divs,
      // so the chip pass has to widen the selector. Shortest match wins = innermost element.
      const selector = broad
        ? 'button,[role="tab"],[role="button"],summary,a,div,li'
        : 'button,[role="tab"],[role="button"],summary,a';
      const elements = Array.from(document.querySelectorAll(selector))
        .map((element) => ({ element, text: (element.textContent || "").trim() }))
        .filter((item) => item.text && re.test(item.text) && item.text.length <= 60)
        .sort((left, right) => left.text.length - right.text.length);
      if (!elements.length) return null;
      elements[0].element.click();
      return elements[0].text;
    },
    { source: pattern, broad: wide }
  );

const waitFor = async (pattern, seconds = 12) => {
  for (let elapsed = 0; elapsed < seconds * 4; elapsed += 1) {
    const found = await page.evaluate(
      (source) => new RegExp(source, "i").test(document.body.innerText || ""),
      pattern
    );
    if (found) return true;
    await page.waitForTimeout(250);
  }
  return false;
};

if (!(await waitFor("CLOSURE PROFILES", 3))) {
  const task = await clickText(arg("task", "自改进 agent 的 archive|证据驱动科研写作|本地研究者"));
  await waitFor("CLOSURE PROFILES", 8);
  if (task) console.log("task clicked: " + task);
}

// The inventory lives behind the PROJECTS tab; the chips behind it are plain divs.
const tab = await clickText("^PROJECTS$");
if (tab) console.log("tab clicked: " + tab);
await page.waitForTimeout(1200);
const picked = await clickText(projectHint, true);
if (picked) console.log("project clicked: " + picked);
// "CLOSURE PROFILES" is already on screen from the previously selected project, so the only
// meaningful wait is for the newly selected project's own rows to arrive.
const expected = arg("expect", "search_study");
const expectFound = await waitFor(expected, 25);
// In dev, React re-runs the project effect once (StrictMode), which clears the panels and
// refetches; capturing immediately can land in that empty window.
await page.waitForTimeout(1500);

const closure = await page.evaluate(() => {
  // Both the closure inventory and the autopilot strip use this class; the heading is a child,
  // so selecting by class avoids grabbing the header-only node.
  const panels = Array.from(document.querySelectorAll(".closure-inventory"));
  return panels.length ? panels.map((panel) => panel.innerText).join("\n---\n") : null;
});

const report = {
  url,
  launchChannel: launch.channel || "bundled chromium",
  taskClicked: picked,
  expected,
  expectFound,
  replicationRendered: /replication/i.test(closure || ""),
  generalizesRendered: /泛化|generaliz/i.test(closure || ""),
  closureText: closure ? closure.slice(0, 2400) : "(closure panel not rendered)",
};
console.log(JSON.stringify(report, null, 1));
if (!closure) {
  console.log("clickable labels seen: " + JSON.stringify((await texts()).slice(0, 40)));
}
await browser.close();
process.exit(closure ? 0 : 1);
