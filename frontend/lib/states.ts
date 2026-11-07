export const TERMINAL_STATES = [
  "REJECTED",
  "FAILED",
  "CANCELLED",
  "PR_CREATED",
] as const;

export type TerminalState = (typeof TERMINAL_STATES)[number];

const TERMINAL = new Set<string>(TERMINAL_STATES);

export type Tick = "pine" | "brick" | "none";
export type StateTone = "pine" | "brick" | "ink";

export function isTerminal(state: string): boolean {
  return TERMINAL.has(state);
}

export function tickFor(state: string): Tick {
  if (state === "AWAITING_APPROVAL") return "pine";
  if (state === "FAILED") return "brick";
  return "none";
}

export function stateTone(state: string): StateTone {
  if (state === "AWAITING_APPROVAL") return "pine";
  if (state === "FAILED") return "brick";
  return "ink";
}
