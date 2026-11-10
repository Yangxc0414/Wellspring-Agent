import { useMemo } from "react";

export interface DagNode {
  id: string;
  kind: string;
  label: string;
  shortHash: string;
  stage: string;
  dependencies: string[];
}

export interface DagGroup {
  stage: string;
  label: string;
  nodes: DagNode[];
}

const COL_W = 168;
const ROW_H = 56;
const NODE_W = COL_W - 26;
const NODE_H = ROW_H - 16;
const PAD = 14;

/**
 * A layered left-to-right DAG of the lineage snapshot.
 *
 * The page previously called itself a "dependency graph" while drawing only a vertical rail with no
 * edges, so the actual dependency direction lived only in a side panel. Stages are already a
 * topological layering, which makes a honest layered drawing cheap: one column per stage, one row
 * per node, and an arrow from each dependency to its dependent. Arrows point downstream (the
 * direction impact propagates), matching the UPSTREAM/DOWNSTREAM lists in the detail panel.
 *
 * This is a visual overview; the interactive, screen-reader-friendly node buttons remain in the
 * stage list below, so nothing here is the only way to reach a node.
 */
export function LineageDag({
  groups,
  selectedId,
  staleIds,
  changedIds,
  onSelect
}: {
  groups: DagGroup[];
  selectedId: string;
  staleIds: Set<string>;
  changedIds: Set<string>;
  onSelect: (id: string) => void;
}) {
  const layout = useMemo(() => {
    const pos = new Map<string, { x: number; y: number; node: DagNode }>();
    groups.forEach((group, gi) => {
      group.nodes.forEach((node, ni) => {
        pos.set(node.id, { x: PAD + gi * COL_W, y: PAD + ni * ROW_H, node });
      });
    });
    const edges: Array<{ from: string; to: string; x1: number; y1: number; x2: number; y2: number }> = [];
    for (const { node } of pos.values()) {
      const to = pos.get(node.id)!;
      for (const dep of node.dependencies ?? []) {
        const from = pos.get(dep);
        if (!from) continue;
        edges.push({
          from: dep,
          to: node.id,
          x1: from.x + NODE_W,
          y1: from.y + NODE_H / 2,
          x2: to.x,
          y2: to.y + NODE_H / 2
        });
      }
    }
    const maxRows = Math.max(1, ...groups.map((g) => g.nodes.length));
    return {
      pos,
      edges,
      width: PAD * 2 + groups.length * COL_W,
      height: PAD * 2 + maxRows * ROW_H
    };
  }, [groups]);

  return (
    <div className="lineage-dag">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="img"
        aria-label={` lineage 依赖图：${groups.length} 层、${layout.pos.size} 个节点、${layout.edges.length} 条上游到下游的边；箭头指向受影响的下游`}
        style={{ width: "100%", height: "auto" }}
      >
        <defs>
          <marker id="lineage-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
          </marker>
        </defs>
        {layout.edges.map((edge) => {
          const stale = staleIds.has(edge.to);
          const midX = (edge.x1 + edge.x2) / 2;
          return (
            <path
              key={`${edge.from}->${edge.to}`}
              className={`lineage-dag-edge${stale ? " is-stale" : ""}`}
              d={`M ${edge.x1} ${edge.y1} C ${midX} ${edge.y1}, ${midX} ${edge.y2}, ${edge.x2 - 2} ${edge.y2}`}
              markerEnd="url(#lineage-arrow)"
              fill="none"
            />
          );
        })}
        {[...layout.pos.values()].map(({ x, y, node }) => {
          const stale = staleIds.has(node.id);
          const changed = changedIds.has(node.id);
          return (
            <g
              key={node.id}
              className={`lineage-dag-node${stale ? " is-stale" : ""}${changed ? " is-changed" : ""}${selectedId === node.id ? " is-selected" : ""}`}
              transform={`translate(${x},${y})`}
              onClick={() => onSelect(node.id)}
            >
              <rect width={NODE_W} height={NODE_H} rx="5" />
              <text x="7" y="15" className="lineage-dag-kind">{node.kind.toUpperCase()}</text>
              <text x="7" y="30" className="lineage-dag-label">{node.label.slice(0, 18)}</text>
            </g>
          );
        })}
      </svg>
      <p className="lineage-dag-note">
        {layout.edges.length} 条边 · 箭头从上游指向下游（变更影响传播方向）；点击节点查看详情，键盘与读屏请用下方阶段列表。
      </p>
    </div>
  );
}
