import type { PersistedWorkspace } from "../domain/types";

export interface WorkspaceAdapter {
  readonly kind: "static" | "runtime";
  readonly label: string;
  load(): PersistedWorkspace | null;
  save(snapshot: PersistedWorkspace): void;
  clear(): void;
}
