"use client";

import { useEffect, useRef, useState } from "react";
import Trace from "@/components/Trace";
import { streamRun, type AgentKind, type Preset, type RunEvent } from "@/lib/events";

const AGENT_LABEL: Record<AgentKind, string> = {
  c1: "Lean (C1: tool retrieval + token budget)",
  baseline: "Baseline (stock smolagents)",
};

const OUTCOME_LABEL: Record<string, string> = {
  pass: "Passed the BFCL checker",
  checker_fail: "Failed the BFCL checker",
  provider_reject: "Stopped: the LLM provider rejected a response",
  request_too_large: "Stopped: request exceeded the free tier's per-request limit",
  rate_limited: "Stopped: free-tier rate limit reached",
  provider_unavailable: "Stopped: the LLM provider is temporarily unavailable",
  timeout: "Stopped: demo time limit reached",
  step_cap: "Stopped: too many steps in one turn",
  error: "Stopped: unexpected error",
};

export default function Home() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [agent, setAgent] = useState<AgentKind>("c1");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch("/api/presets")
      .then((r) => r.json())
      .then((d) => {
        setPresets(d.presets);
        setSelected(d.presets[0]?.id ?? null);
      })
      .catch(() => setError("Could not reach the API."));
  }, []);

  async function run() {
    if (!selected) return;
    setEvents([]);
    setError(null);
    setRunning(true);
    abortRef.current = new AbortController();
    try {
      await streamRun(selected, agent, (e) => setEvents((prev) => [...prev, e]), abortRef.current.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const start = events.find((e) => e.type === "run_start");
  const done = events.find((e) => e.type === "done");
  const runError = events.find((e) => e.type === "run_error");
  const streamCut = !running && events.length > 0 && !done;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10 sm:px-6">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Lean Agents</h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Watch a tool-using LLM agent work through a{" "}
          <a className="underline" href="https://gorilla.cs.berkeley.edu/leaderboard.html" target="_blank" rel="noreferrer">
            BFCL
          </a>{" "}
          multi-turn task, step by step, on free-tier APIs. The simulated APIs are sandboxed; the result is scored by
          BFCL&apos;s own state checker.
        </p>
        <p className="mt-2 text-sm text-zinc-500">
          Compare the stock smolagents agent with the lean agent. C1 offers each step only the relevant tools and
          keeps requests small, which matters on a free tier with an 8K tokens-per-minute limit.{" "}
          <a className="underline" href="https://github.com/RachitaPant/Lean-Agents" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </p>
      </header>

      <section aria-label="Pick a task" className="mb-6 grid gap-3 sm:grid-cols-2">
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => setSelected(p.id)}
            disabled={running}
            className={`rounded-xl border p-4 text-left transition disabled:opacity-60 ${
              selected === p.id
                ? "border-zinc-900 ring-1 ring-zinc-900 dark:border-zinc-100 dark:ring-zinc-100"
                : "border-zinc-200 hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
            }`}
          >
            <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
              <span className="rounded bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">{p.domain}</span>
              <span>
                {p.turns.length} turn{p.turns.length > 1 ? "s" : ""}
              </span>
            </div>
            <div className="font-medium">{p.title}</div>
            <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">{p.turns[0]}</p>
          </button>
        ))}
      </section>

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <div role="radiogroup" aria-label="Agent" className="flex rounded-lg border border-zinc-200 p-0.5 text-sm dark:border-zinc-800">
          {(Object.keys(AGENT_LABEL) as AgentKind[]).map((k) => (
            <button
              key={k}
              role="radio"
              aria-checked={agent === k}
              disabled={running}
              onClick={() => setAgent(k)}
              className={`rounded-md px-3 py-1.5 disabled:opacity-60 ${
                agent === k ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-600 dark:text-zinc-400"
              }`}
            >
              {AGENT_LABEL[k]}
            </button>
          ))}
        </div>
        <button
          onClick={run}
          disabled={!selected || running}
          className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {running ? "Running…" : "Run agent"}
        </button>
        {running && (
          <button onClick={() => abortRef.current?.abort()} className="text-sm text-zinc-500 underline">
            Stop watching
          </button>
        )}
        {start && (
          <span className="text-sm text-zinc-500">
            {start.model} · {start.tools} tools available
          </span>
        )}
      </div>

      {error && (
        <p role="alert" className="mb-6 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {error}
        </p>
      )}

      <Trace events={events} running={running} />

      {streamCut && (
        <p className="mt-6 text-sm text-zinc-500">The stream ended before the run finished (stopped or timed out).</p>
      )}

      {done && done.type === "done" && (
        <section
          aria-label="Result"
          className={`mt-6 rounded-xl border px-4 py-4 ${
            done.success
              ? "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950"
              : "border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950"
          }`}
        >
          <div className="font-semibold">{OUTCOME_LABEL[done.outcome] ?? done.outcome}</div>
          {runError && runError.type === "run_error" && (
            <p className="mt-1 break-words font-mono text-xs">{runError.message.slice(0, 300)}</p>
          )}
          {!done.success && !runError && done.checker.error_message && (
            <p className="mt-1 text-sm">BFCL checker: {done.checker.error_message}</p>
          )}
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-zinc-500">LLM calls</dt>
              <dd className="font-medium">{done.llm_calls}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Prompt tokens</dt>
              <dd className="font-medium">{done.prompt_tokens.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Output tokens</dt>
              <dd className="font-medium">{done.completion_tokens.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Time</dt>
              <dd className="font-medium">{done.latency_s}s</dd>
            </div>
          </dl>
        </section>
      )}
    </main>
  );
}
