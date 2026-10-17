import type { RunEvent } from "@/lib/events";
import { formatValue } from "@/lib/labels";
import { SparkIcon, ToolIcon } from "@/components/icons";

type ToolItem = { kind: "tool"; name: string; args: unknown; observation?: string };
type FixItem = { kind: "fix"; message: string };
type Turn = { index: number; user: string; items: (ToolItem | FixItem)[]; answer?: string; done: boolean };

// Errors the agent made that were fed back to it (C2) or rejected by smolagents' own checks
const FIXABLE = new Set(["AgentToolCallError", "AgentParsingError", "AgentToolExecutionError"]);

function buildTurns(events: RunEvent[]): Turn[] {
  const turns: Turn[] = [];
  for (const e of events) {
    if (e.type === "turn_start") turns.push({ index: e.turn, user: e.user, items: [], done: false });
    const t = turns.at(-1);
    if (!t) continue;
    if (e.type === "tool_call") t.items.push({ kind: "tool", name: e.name, args: e.args });
    if (e.type === "tool_result") {
      const call = [...t.items]
        .reverse()
        .find((i): i is ToolItem => i.kind === "tool" && i.name === e.name && i.observation === undefined);
      if (call) call.observation = e.observation;
    }
    if (e.type === "step" && e.error && FIXABLE.has(e.error_type ?? "")) {
      t.items.push({ kind: "fix", message: e.error.split("\nNow let's retry")[0] });
    }
    if (e.type === "turn_end") {
      t.answer = e.answer;
      t.done = true;
    }
  }
  return turns;
}

/** Models sometimes type a final_answer call as plain text; show just its answer. */
function readableAnswer(text: string): string {
  const t = text.trim();
  if (!t.startsWith("{")) return text;
  try {
    const obj = JSON.parse(t);
    const answer = obj?.arguments?.answer ?? obj?.answer;
    return typeof answer === "string" ? answer : text;
  } catch {
    return text;
  }
}

function Args({ args }: { args: unknown }) {
  if (!args || typeof args !== "object" || Object.keys(args).length === 0) {
    return <span className="text-xs text-zinc-500">no inputs</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(args as Record<string, unknown>).map(([k, v]) => (
        <span
          key={k}
          className="rounded-md bg-zinc-100 px-2 py-0.5 font-mono text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
        >
          <span className="text-zinc-500">{k}:</span> {formatValue(v)}
        </span>
      ))}
    </div>
  );
}

export default function Trace({ events, running }: { events: RunEvent[]; running: boolean }) {
  const turns = buildTurns(events);
  return (
    <ol className="space-y-8" aria-label="What the agent did">
      {turns.map((turn, ti) => {
        const live = running && ti === turns.length - 1 && !turn.done;
        return (
          <li key={turn.index} className="space-y-3">
            {/* the user's request */}
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-3 text-sm leading-relaxed text-white shadow-sm">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-indigo-200">
                  Request {turn.index + 1}
                </div>
                {turn.user}
              </div>
            </div>

            {/* the agent's actions */}
            {turn.items.map((item, i) =>
              item.kind === "tool" ? (
                <div
                  key={i}
                  className="animate-rise rounded-xl border border-zinc-200 bg-white p-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <div className="mb-2 flex items-center gap-2 text-sm">
                    <span className="grid size-6 place-items-center rounded-md bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                      <ToolIcon className="size-3.5" />
                    </span>
                    <span className="text-zinc-500">Used tool</span>
                    <code className="font-mono font-semibold text-emerald-700 dark:text-emerald-400">{item.name}</code>
                  </div>
                  <Args args={item.args} />
                  {item.observation !== undefined && (
                    <details className="group mt-2">
                      <summary className="cursor-pointer list-none text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300">
                        <span className="group-open:hidden">Show what the app returned ▸</span>
                        <span className="hidden group-open:inline">Hide what the app returned ▾</span>
                      </summary>
                      <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-zinc-50 p-2 font-mono text-xs whitespace-pre-wrap break-all text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
                        {item.observation}
                      </pre>
                    </details>
                  )}
                </div>
              ) : (
                <div
                  key={i}
                  className="animate-rise flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
                >
                  <SparkIcon className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <div className="font-medium">The agent made a mistake and was told how to fix it</div>
                    <div className="mt-0.5 text-xs opacity-80">{item.message.slice(0, 220)}</div>
                  </div>
                </div>
              ),
            )}

            {live && (
              <div className="flex items-center gap-2 text-sm text-zinc-500" role="status">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-indigo-500" />
                </span>
                The agent is thinking…
              </div>
            )}

            {/* the agent's reply */}
            {turn.answer && (
              <div className="animate-rise flex">
                <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white px-4 py-3 text-sm leading-relaxed shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-zinc-500">Agent replied</div>
                  {readableAnswer(turn.answer)}
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
