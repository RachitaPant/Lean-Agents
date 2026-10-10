import type { RunEvent } from "@/lib/events";

type ToolItem = { kind: "tool"; name: string; args: unknown; observation?: string };
type StepItem = Extract<RunEvent, { type: "step" }> & { kind: "step" };
type Turn = { index: number; user: string; items: (ToolItem | StepItem)[]; answer?: string };

function buildTurns(events: RunEvent[]): Turn[] {
  const turns: Turn[] = [];
  for (const e of events) {
    if (e.type === "turn_start") turns.push({ index: e.turn, user: e.user, items: [] });
    const t = turns[turns.length - 1];
    if (!t) continue;
    if (e.type === "tool_call") t.items.push({ kind: "tool", name: e.name, args: e.args });
    if (e.type === "tool_result") {
      const call = [...t.items].reverse().find(
        (i): i is ToolItem => i.kind === "tool" && i.name === e.name && i.observation === undefined,
      );
      if (call) call.observation = e.observation;
    }
    if (e.type === "step") t.items.push({ ...e, kind: "step" });
    if (e.type === "turn_end") t.answer = e.answer;
  }
  return turns;
}

function formatArgs(args: unknown): string {
  if (args && typeof args === "object") {
    return Object.entries(args as Record<string, unknown>)
      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
      .join(", ");
  }
  return String(args ?? "");
}

export default function Trace({ events, running }: { events: RunEvent[]; running: boolean }) {
  const turns = buildTurns(events);
  const start = events.find((e) => e.type === "run_start");
  const totalTools = start && start.type === "run_start" ? start.tools : undefined;
  return (
    <ol className="space-y-6">
      {turns.map((turn, ti) => (
        <li key={turn.index} className="rounded-xl border border-zinc-200 dark:border-zinc-800">
          <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Turn {turn.index + 1} · user
            </div>
            <p className="text-sm leading-relaxed">{turn.user}</p>
          </div>
          <div className="space-y-2 px-4 py-3">
            {turn.items.length === 0 && running && ti === turns.length - 1 && (
              <p className="animate-pulse text-sm text-zinc-500">Thinking…</p>
            )}
            {turn.items.map((item, i) =>
              item.kind === "tool" ? (
                <div key={i} className="rounded-lg bg-zinc-100 px-3 py-2 dark:bg-zinc-900">
                  <code className="block break-all font-mono text-sm">
                    <span className="font-semibold text-emerald-700 dark:text-emerald-400">{item.name}</span>(
                    {formatArgs(item.args)})
                  </code>
                  {item.observation !== undefined && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-zinc-500">result</summary>
                      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-zinc-700 dark:text-zinc-300">
                        {item.observation}
                      </pre>
                    </details>
                  )}
                </div>
              ) : (
                <div key={i} className="flex flex-wrap items-center gap-x-3 text-xs text-zinc-500">
                  <span>step {item.step}</span>
                  {item.tools_offered !== undefined && totalTools !== undefined && (
                    <span>
                      {item.tools_offered - 1} of {totalTools} tools offered
                    </span>
                  )}
                  <span>
                    {item.prompt_tokens.toLocaleString()} in / {item.completion_tokens.toLocaleString()} out tokens
                  </span>
                  {item.duration_s !== null && <span>{item.duration_s}s</span>}
                  {item.error && (
                    <span className="rounded bg-amber-100 px-1.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                      {item.error.slice(0, 160)}
                    </span>
                  )}
                </div>
              ),
            )}
            {turn.answer !== undefined && turn.answer !== "" && (
              <p className="border-l-2 border-zinc-300 pl-3 text-sm text-zinc-700 dark:border-zinc-700 dark:text-zinc-300">
                {turn.answer}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
