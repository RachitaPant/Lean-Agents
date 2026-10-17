// Plain-language labels shared by the page and the trace view.

/** BFCL API class → what a visitor would call it. */
export const APP_NAME: Record<string, string> = {
  GorillaFileSystem: "File system",
  TradingBot: "Stock trading app",
  VehicleControlAPI: "Car controls",
  TravelAPI: "Travel booking",
  MessageAPI: "Messaging app",
  TwitterAPI: "Social media app",
  TicketAPI: "Support tickets",
  MathAPI: "Calculator",
};

export type OutcomeText = { title: string; detail: string };

/** Run outcome (agent/runner.py) → a verdict a non-expert understands. */
export const OUTCOME: Record<string, OutcomeText> = {
  pass: {
    title: "Passed",
    detail: "The grader replayed the agent's actions and every app ended up exactly where the correct solution leaves it.",
  },
  checker_fail: {
    title: "Failed the grader",
    detail: "The agent finished, but the apps did not end up in the right state (a wrong action, a missing one, or a wrong value).",
  },
  provider_reject: {
    title: "Stopped: invalid tool call",
    detail: "The AI produced a call the AI service refused, for example to a tool that doesn't exist. The stock agent can't recover from this.",
  },
  request_too_large: {
    title: "Stopped: message too big",
    detail: "The conversation grew past the free tier's size limit for a single request (8,000 tokens). This is what the lean agent is built to avoid.",
  },
  rate_limited: {
    title: "Stopped: free-tier limit reached",
    detail: "The free AI service's usage limit was reached. Please try again in a minute.",
  },
  provider_unavailable: {
    title: "Stopped: AI service unavailable",
    detail: "The AI service was briefly unavailable. Please try again.",
  },
  timeout: {
    title: "Stopped: demo time limit",
    detail: "The demo stops runs after about 3 minutes to stay within free hosting limits.",
  },
  step_cap: {
    title: "Stopped: too many steps",
    detail: "The agent kept going without finishing the request, so the run was stopped.",
  },
  error: {
    title: "Stopped: unexpected error",
    detail: "Something went wrong outside the agent. Please try again.",
  },
};

export function formatValue(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => String(x)).join(", ");
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}
