/**
 * Host-as-Model handoff client.
 *
 * A bound keyless `host_agent` profile makes every generation stage suspend on a durable
 * turn instead of calling an external API. This client reads those turns and submits the
 * answer produced by the agent sitting in front of the workbench. A submitted answer is
 * capability output, never a signature: gates and audits are unchanged.
 */

import { authHeaders, describeAuthRefusal } from "./runtimeAuth";

const runtimeBase = (import.meta.env.VITE_RUNTIME_URL ?? "").replace(/\/$/, "");

export interface HostModelRequest {
  system: string;
  turns: { role: string; content: string }[];
}

export interface HostModelReceipt {
  turn_id: string;
  module: string;
  purpose: string;
  messages_sha256: string;
  text_sha256: string;
  host_label: string;
  submitted_at: string;
}

export interface HostModelTurn {
  turn_id: string;
  status: "pending" | "responded" | "expired" | "cancelled";
  module: string;
  purpose: string;
  profile_id: string;
  messages_sha256: string;
  created_at: string;
  expires_at: string;
  reject_count: number;
  binding: Record<string, string>;
  expects: {
    json: boolean;
    object: boolean;
    array_field: string;
    min_items: number;
    require_keys: string[];
  };
  last_rejection?: { errors: string[]; at: string } | null;
  receipt?: HostModelReceipt | null;
  request?: HostModelRequest;
}

export interface HostModelQueue {
  schema_version: string;
  counts: Record<string, number>;
  returned: number;
  turns: HostModelTurn[];
  how_to_respond: string;
  boundary: string;
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 6000): Promise<T> {
  if (__STATIC_ONLY__) throw new Error("runtime disabled in static build");
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(runtimeBase + path, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...authHeaders(),
        ...(init?.headers ?? {})
      }
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const refusal = describeAuthRefusal(response.status, detail);
      throw new Error(refusal || `${response.status} ${detail.slice(0, 200)}`.trim());
    }
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timer);
  }
}

export interface CriticSupply {
  supply_key: string;
  profile_id: string;
  provider_id: string;
  model: string;
  kind: string;
  keyless: boolean;
}

export interface CriticPanel {
  schema_version: string;
  roles: string[];
  distinct_supplies: number;
  usable_profiles: string[];
  supplies: CriticSupply[];
  proposer_profile: string;
  proposer_excluded: boolean;
  panel_possible: boolean;
  suggested: Record<string, string>;
  missing_supplies: number;
  note: string;
  boundary: string;
}

export async function loadCriticPanel(): Promise<CriticPanel> {
  return request<CriticPanel>("/api/host-model/panel");
}

export async function loadHostModelTurns(  status = "",
  limit = 20
): Promise<HostModelQueue> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (status) query.set("status", status);
  return request<HostModelQueue>(`/api/host-model/turns?${query.toString()}`);
}

export async function respondHostModelTurn(
  turnId: string,
  text: string,
  hostLabel: string
): Promise<{ accepted: boolean; errors?: string[]; receipt?: HostModelReceipt; note?: string }> {
  return request("/api/host-model/respond", {
    method: "POST",
    body: JSON.stringify({ turn_id: turnId, text, host_label: hostLabel })
  });
}
