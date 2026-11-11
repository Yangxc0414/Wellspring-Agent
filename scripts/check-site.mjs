import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "site");
const failures = [];

function check(condition, message) {
  if (!condition) failures.push(message);
}

function read(relative) {
  return fs.readFileSync(path.join(root, relative), "utf8");
}

for (const file of [
  "index.html",
  "app/index.html",
  "404.html",
  "manifest.webmanifest",
  ".nojekyll"
]) {
  check(fs.existsSync(path.join(root, file)), `missing ${file}`);
}

const appHtml = read("app/index.html");
const assetRefs = [
  ...appHtml.matchAll(/(?:src|href)="\.\/(assets\/[^"]+)"/g)
].map((match) => match[1]);
check(assetRefs.length >= 2, "app/index.html has fewer than 2 local asset refs");
for (const ref of assetRefs) {
  check(fs.existsSync(path.join(root, "app", ref)), `missing app asset ${ref}`);
}

const appAssets = path.join(root, "app", "assets");
const jsFiles = fs.existsSync(appAssets)
  ? fs.readdirSync(appAssets).filter((file) => file.endsWith(".js"))
  : [];
check(jsFiles.length > 0, "app/assets has no JavaScript bundle");
const appJs = jsFiles
  .map((file) => fs.readFileSync(path.join(appAssets, file), "utf8"))
  .join("\n");
check(
  appJs.includes("runtime disabled in static build"),
  "app bundle is not built in static mode (missing static runtime guard)"
);

const landing = read("index.html");
check(landing.includes("./app/"), "landing page does not link to ./app/");
check(fs.existsSync(path.join(root, "app", "favicon.svg")), "missing app/favicon.svg");

// Every hand-written demo page must carry the shared legibility layer: without it
// the pages revert to unexplained ids, hashes and English abbreviations.
const legibilityPages = [
  ["index.html", "home"],
  ["innovation/index.html", "innovation"],
  ["rsi/index.html", "rsi"],
  ["qoder/index.html", "qoder"],
  ["models/index.html", "models"],
  ["live/index.html", "live"],
  ["agent/index.html", "agent"],
  ["demo/index.html", "demo"]
];
check(fs.existsSync(path.join(root, "assets/demo-legibility.css")), "missing shared legibility CSS");
check(fs.existsSync(path.join(root, "assets/demo-legibility.js")), "missing shared legibility JS");
for (const [file, page] of legibilityPages) {
  const html = read(file);
  check(html.includes("demo-legibility.css"), `${file} missing shared legibility CSS`);
  check(html.includes("demo-legibility.js"), `${file} missing shared legibility JS`);
  check(html.includes(`data-dl-page="${page}"`), `${file} missing data-dl-page=${page}`);
}
const demoSource = path.join(root, "..", "demo", "index.html");
check(
  fs.existsSync(demoSource) && fs.readFileSync(demoSource, "utf8").includes("demo-legibility.js"),
  "demo/index.html source missing shared legibility JS (build-site would overwrite the copy)"
);

if (failures.length) {
  console.error("site check failed:");
  for (const failure of failures) console.error(" - " + failure);
  process.exit(1);
}

console.log(
  `site check ok: ${assetRefs.length} app assets, ${jsFiles.length} JS bundle(s), static mode confirmed, ${legibilityPages.length} demo pages legible`
);
