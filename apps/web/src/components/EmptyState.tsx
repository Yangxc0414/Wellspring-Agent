import type { ReactNode } from "react";

import { Icon } from "./Icon";
import type { IconName } from "./Icon";

/**
 * One empty-state shape for the whole app.
 *
 * Empty surfaces used to be a bare <p> carrying a class with no CSS rule at all
 * (`.context-note` had no definition), so PROJECTS rendered a screen of white
 * with one grey line and read as broken rather than empty. An empty state owes
 * the viewer three things: what is missing, why, and what they can do next.
 *
 * The block variant reuses `.context-empty-card`, an existing styled-but-unused
 * empty card, so there is one visual language instead of two. `tone="note"` is
 * the compact inline variant for panels that are otherwise populated.
 */
export function EmptyState({
  icon = "evidence",
  title,
  children,
  action,
  tone = "block",
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "block" | "note";
}) {
  if (tone === "note") {
    return (
      <div className="empty-state is-note">
        <Icon name={icon} size={12} />
        <div>
          <b>{title}</b>
          {children ? <p>{children}</p> : null}
        </div>
        {action ? <div className="empty-state-action">{action}</div> : null}
      </div>
    );
  }
  return (
    <div className="context-empty-card empty-state">
      <Icon name={icon} size={18} />
      <b className="empty-state-title">{title}</b>
      {children ? <p>{children}</p> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
