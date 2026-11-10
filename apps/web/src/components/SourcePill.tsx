/** One source badge for every settings/overview panel.
 *
 * AgentManagement, WorkspaceSettings and OrchestrationOverview used to carry three
 * near-identical copies that differed only in the label for `snapshot`. Keeping the
 * wording in one place means a new source kind cannot silently diverge across pages.
 */
export type SourceKind = "runtime" | "snapshot" | "local";

const DEFAULT_LABELS: Record<SourceKind, string> = {
  runtime: "LIVE RUNTIME",
  snapshot: "SNAPSHOT",
  local: "LOCAL DRAFT"
};

export function SourcePill({
  source,
  labels,
  emptyLabel = "STATIC"
}: {
  source: SourceKind | null;
  labels?: Partial<Record<SourceKind, string>>;
  emptyLabel?: string;
}) {
  if (!source) return <span className="settings-source">{emptyLabel}</span>;
  const text = labels?.[source] ?? DEFAULT_LABELS[source];
  return (
    <span className={`settings-source${source === "runtime" ? " is-live" : ""}`}>{text}</span>
  );
}
