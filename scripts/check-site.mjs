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

if (failures.length) {
  console.error("site check failed:");
  for (const failure of failures) console.error(" - " + failure);
  process.exit(1);
}

console.log(
  `site check ok: ${assetRefs.length} app assets, ${jsFiles.length} JS bundle(s), static mode confirmed`
);
