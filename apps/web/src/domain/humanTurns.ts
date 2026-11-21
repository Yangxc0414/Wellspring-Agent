import type { Message } from "./types";

/**
 * The human's own words inside a task transcript (role === "user"), projected
 * per stage. READ-ONLY derivation with the same span rule as
 * demoStageSpans: untagged messages are absorbed into the preceding staged
 * message's span, so a user turn like「G1：收敛到 H1…」lands on the stage it
 * belongs to. Turns spoken before the first stage tag have stage=null (开场).
 * Nothing here invents content — the panel quotes the transcript verbatim.
 */

export interface HumanTurn {
  id: string;
  at: string;
  text: string;
  /** Stage the turn sits in (null = before the first stage tag). */
  stage: string | null;
}

export function humanTurns(messages: Message[]): HumanTurn[] {
  const turns: HumanTurn[] = [];
  let current: string | null = null;
  for (const item of messages) {
    if (item.stage) current = item.stage;
    if (item.role === "user") {
      turns.push({ id: item.id, at: item.at, text: item.text, stage: current });
    }
  }
  return turns;
}

export function turnsByStage(turns: HumanTurn[]): Record<string, HumanTurn[]> {
  const grouped: Record<string, HumanTurn[]> = {};
  for (const turn of turns) {
    const key = turn.stage ?? "";
    (grouped[key] ??= []).push(turn);
  }
  return grouped;
}

/** User turns inside one stage span ("" = the pre-stage opening). */
export function turnsForStage(turns: HumanTurn[], stageId: string): HumanTurn[] {
  const key = stageId === "" ? "" : stageId;
  return turnsByStage(turns)[key] ?? [];
}

/**
 * The human's own decision line for a gate, if they stated one in the stage
 * that owns the gate (e.g.「G1：收敛到 H1…」inside S2–S3). Only lines that
 * begin with the gate id count — questions like「这条现在能签吗？」are NOT
 * decisions and must never be pre-filled as a human_reason.
 */
export function gateDecisionQuote(turns: HumanTurn[], stageId: string, gate: string): HumanTurn | null {
  const prefix = `${gate}：`;
  return (
    turnsForStage(turns, stageId).find((turn) => turn.text.trimStart().startsWith(prefix)) ?? null
  );
}
