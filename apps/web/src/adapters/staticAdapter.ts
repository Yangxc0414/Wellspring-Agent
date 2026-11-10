import { builtinSkills, STORAGE_KEY, STORAGE_VERSION } from "../domain/catalog";
import { emptyEvaluation } from "../domain/seed";
import type { PersistedWorkspace, Skill } from "../domain/types";
import { isoDateOffset } from "../domain/utils";
import type { WorkspaceAdapter } from "./types";

export function normalizeSkill(skill: Skill & { enabled?: boolean }): Skill {
  const requested =
    skill.activation ??
    (skill.enabled === false ? "off" : skill.source === "builtin" ? "auto" : "manual");
  return {
    ...skill,
    activation: requested === "auto" && skill.source !== "builtin" ? "manual" : requested
  };
}

export function isSnapshot(value: unknown): value is PersistedWorkspace {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<PersistedWorkspace>;
  return (
    candidate.version === STORAGE_VERSION &&
    typeof candidate.selectedTaskId === "string" &&
    typeof candidate.activeWorkspaceId === "string" &&
    Array.isArray(candidate.workspaces) &&
    candidate.workspaces.length > 0 &&
    Array.isArray(candidate.tasks) &&
    candidate.tasks.length > 0 &&
    Array.isArray(candidate.plugins)
  );
}

const BACKUP_SUFFIX = ".backup-v";

/**
 * A schema-version mismatch used to silently discard the whole workspace (load →
 * null → seed data). Now the old payload is parked under a versioned backup key
 * first, so a migration bug can never lose user work beyond recovery.
 */
function parkIncompatibleSnapshot(parsed: unknown, version: unknown): void {
  if (!parsed || typeof parsed !== "object") return;
  try {
    const key = `${STORAGE_KEY}${BACKUP_SUFFIX}${String(version ?? "unknown")}`;
    const existing = localStorage.getItem(key);
    if (!existing) localStorage.setItem(key, JSON.stringify(parsed));
  } catch {
    /* quota / private mode: nothing more we can do here */
  }
}

export const staticAdapter: WorkspaceAdapter = {
  kind: "static",
  label: "STATIC · localStorage",
  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed: unknown = JSON.parse(raw);
      if (!isSnapshot(parsed)) {
        const version = (parsed as { version?: unknown } | null)?.version;
        if (version !== STORAGE_VERSION && version !== undefined) {
          parkIncompatibleSnapshot(parsed, version);
        }
        return null;
      }
      parsed.tasks = parsed.tasks.map((task) => {
        const usage = task.usage ?? {};
        const usageDays = task.usageDays ?? (Object.keys(usage).length ? { [isoDateOffset(0)]: usage } : {});
        return {
          ...task,
          access: task.access ?? "ask",
          evaluation: task.evaluation ?? emptyEvaluation(),
          usage,
          usageDays,
          auto: { ...task.auto, running: false, paused: false }
        };
      });
      if (!Array.isArray(parsed.skills) || parsed.skills.length === 0) {
        parsed.skills = builtinSkills();
      } else {
        parsed.skills = parsed.skills.map((skill) =>
          normalizeSkill(skill as Skill & { enabled?: boolean })
        );
      }
      parsed.memory = Array.isArray(parsed.memory) ? parsed.memory : [];
      parsed.archivedTaskIds = Array.isArray(parsed.archivedTaskIds) ? parsed.archivedTaskIds : [];
      if (!parsed.tasks.some((task) => task.id === parsed.selectedTaskId)) {
        parsed.selectedTaskId = parsed.tasks[0].id;
      }
      return parsed;
    } catch {
      return null;
    }
  },
  save(snapshot) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      /* private mode / quota: the workspace still runs in memory */
    }
  },
  clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
};
