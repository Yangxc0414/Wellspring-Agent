/**
 * Single source of truth for what this build can actually do.
 *
 * Why this file exists: `__STATIC_ONLY__` used to be tested ad hoc inside each
 * adapter. Three of four adapters remembered to bail before fetching; the model
 * runtime did not, so the static demo logged 404s for /api/models. One missed
 * check is enough to make a demo look broken, so the decision now lives here and
 * callers ask this module instead of re-deciding.
 *
 * `__STATIC_ONLY__` stays a literal in this file only, so Vite can still fold it
 * at build time. Everything else reads the derived constants.
 */

/** Runtime (FastAPI) is compiled out of the static Pages build. */
export const runtimeAvailable = !__STATIC_ONLY__;

/**
 * Where each class of work can actually run. Declared once so the UI can label
 * a surface honestly instead of letting the user guess.
 */
export type CapabilityLevel =
  | "real"      // works here and persists in this browser
  | "demo"      // advances local demo state only; never a real artifact
  | "cli"       // requires the local CLI (gate decisions, signatures, exports)
  | "runtime";  // requires the local runtime; unavailable in a static build

export const CAPABILITY_META: Record<CapabilityLevel, { label: string; hint: string }> = {
  real: { label: "本地可用", hint: "改动保存在当前浏览器，刷新后仍在" },
  demo: { label: "演示态", hint: "只推进浏览器里的演示状态，不产生真实产物" },
  cli: { label: "需本地 CLI", hint: "人工门、签名、导出审批只在本地 CLI 执行" },
  runtime: {
    label: "需 runtime",
    hint: "依赖本地 FastAPI runtime；静态构建已在编译期禁用它",
  },
};

/**
 * Throw before issuing a network call this build cannot serve.
 * Callers keep their existing catch path and render their own wording.
 */
export function requireRuntime(what: string): void {
  if (!runtimeAvailable) {
    throw new Error(`${what} requires the local runtime; this build was compiled without it`);
  }
}

/**
 * Turn a caught runtime error into something a viewer can act on.
 *
 * Without this, a static build surfaced raw English like
 * "/api/projects requires the local runtime; this build was compiled without it"
 * inside otherwise Chinese UI. A build-time disable is not a user error, so it
 * gets its own sentence instead of being concatenated after a colon.
 */
export function describeRuntimeError(error: unknown, fallback = "读取失败"): string {
  if (!runtimeAvailable) {
    return "静态演示构建：runtime 在构建时已禁用，这项功能只在本地 CLI 工作台可用。";
  }
  const text = error instanceof Error ? error.message : String(error ?? "");
  return text ? `${fallback}：${text}` : fallback;
}
