/**
 * Runtime credential for the localhost UI.
 *
 * The runtime refuses every mutating route unless the caller presents `Authorization: Bearer
 * <RESEARCH_AGENT_API_TOKEN>` (or comes from loopback with no token configured). This module is
 * the only place that holds that token, and it holds it in memory for the session only: a browser
 * profile is not a secret store, so nothing here touches localStorage, a cookie or a file.
 *
 * Consequence worth stating plainly: with no token configured — the default, since the runtime
 * binds 127.0.0.1 — the UI needs nothing and behaves exactly as before. A token is only required
 * when the runtime was started for remote access, and then the operator pastes it once per
 * session via `window.researchRuntimeAuth.setToken(...)`.
 */

let token = "";

export function setRuntimeToken(value: string): void {
  token = String(value ?? "").trim();
}

export function clearRuntimeToken(): void {
  token = "";
}

export function runtimeToken(): string {
  return token;
}

/** Headers to spread into a fetch init; empty when no token is configured. */
export function authHeaders(): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Turn a refused response into an instruction the operator can act on.
 *
 * The runtime answers 401/403 with a `boundary` explaining the rule; echoing our own text back
 * would hide the fact that the refusal came from the server, so the server's words are kept and
 * only the remedy is added.
 */
export function describeAuthRefusal(status: number, body: string): string {
  if (status !== 401 && status !== 403) return "";
  const detail = body.slice(0, 300).trim();
  const remedy =
    status === 401
      ? "set the runtime token for this session: window.researchRuntimeAuth.setToken('<RESEARCH_AGENT_API_TOKEN>')"
      : "the runtime is loopback-only; open the UI from the same machine or set RESEARCH_AGENT_API_TOKEN";
  return `${detail} — ${remedy}`;
}

declare global {
  interface Window {
    researchRuntimeAuth?: {
      setToken: typeof setRuntimeToken;
      clearToken: typeof clearRuntimeToken;
      hasToken: () => boolean;
    };
  }
}

if (typeof window !== "undefined") {
  window.researchRuntimeAuth = {
    setToken: setRuntimeToken,
    clearToken: clearRuntimeToken,
    hasToken: () => Boolean(token)
  };
}
