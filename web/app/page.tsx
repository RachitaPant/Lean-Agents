"use client";

import { useEffect, useRef, useState } from "react";
import Trace from "@/components/Trace";
import { HowItWorks, PilotResults, WhatIsBfcl } from "@/components/Explainers";
import { CheckIcon, CrossIcon, DomainIcon } from "@/components/icons";
import { streamRun, type AgentKind, type Preset, type RunEvent } from "@/lib/events";
import { APP_NAME, OUTCOME } from "@/lib/labels";

const AGENTS: { kind: AgentKind; name: string; tag?: string; body: string }[] = [
  {
    kind: "lean",
    name: "Lean agent",
    tag: "Our version",
    body: "Shows the AI only the few tools it needs right now, keeps messages small, and helps it fix its own mistakes.",
  },
  {
    kind: "baseline",
    name: "Standard agent",
    body: "The off-the-shelf smolagents agent. Sends every tool's description with every message.",
  },
];

const GITHUB = "https://github.com/RachitaPant/Lean-Agents";

function StepLabel({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <div className="mb-3 flex items-start gap-3">
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
        {n}
      </span>
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:gap-3">
        <h3 className="font-medium">{title}</h3>
        {hint && <span className="text-sm text-zinc-500">{hint}</span>}
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 px-3 py-2 dark:bg-zinc-950" title={hint}>
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

export default function Home() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [agent, setAgent] = useState<AgentKind>("lean");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const runRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    fetch("/api/presets")
      .then((r) => r.json())
      .then((d) => {
        setPresets(d.presets);
        setSelected(d.presets[0]?.id ?? null);
      })
      .catch(() => setError("Could not reach the demo's server. Please refresh in a moment."));
  }, []);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);

  async function run() {
    if (!selected) return;
    setEvents([]);
    setError(null);
    setRunning(true);
    const t = Date.now();
    setStartedAt(t);
    setNow(t);
    runRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    abortRef.current = new AbortController();
    try {
      await streamRun(selected, agent, (e) => setEvents((prev) => [...prev, e]), abortRef.current.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setRunning(false);
      setNow(Date.now());
    }
  }

  const start = events.find((e) => e.type === "run_start");
  const done = events.find((e) => e.type === "done");
  const steps = events.filter((e) => e.type === "step");
  const lastStep = steps.at(-1);
  const tokens = steps.reduce((s, e) => s + (e.type === "step" ? e.prompt_tokens + e.completion_tokens : 0), 0);
  const totalTools = start?.type === "run_start" ? start.tools : undefined;
  const shown = lastStep?.type === "step" && lastStep.tools_offered !== undefined ? lastStep.tools_offered - 1 : undefined;
  const elapsed = startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : 0;
  const streamCut = !running && events.length > 0 && !done;
  const preset = presets.find((p) => p.id === selected);
  const verdict = done?.type === "done" ? OUTCOME[done.outcome] ?? OUTCOME.error : undefined;

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-zinc-200/70 bg-background/80 backdrop-blur dark:border-zinc-800/70">
        <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
          <a href="#" className="font-semibold tracking-tight">
            Lean Agents
          </a>
          <div className="flex items-center gap-4 text-sm text-zinc-600 dark:text-zinc-400">
            <a href="#try" className="hover:text-foreground">Try it</a>
            <a href="#how" className="hidden hover:text-foreground sm:inline">How it works</a>
            <a href="#bfcl" className="hidden hover:text-foreground sm:inline">What is BFCL?</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hover:text-foreground">GitHub ↗</a>
          </div>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 space-y-16 px-4 py-10 sm:px-6">
        {/* hero */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-700 px-6 py-10 text-white shadow-lg sm:px-10">
          <p className="text-sm font-medium text-indigo-200">An independent research project</p>
          <h1 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
            Watch an AI agent use apps to get things done, on a free AI service.
          </h1>
          <p className="mt-4 max-w-2xl leading-relaxed text-indigo-100">
            Give it a request like &ldquo;unlock my car and turn on the headlights&rdquo;. It works through it by
            calling tools in pretend apps. Then an automatic grader checks whether the apps really ended up right.
            The lean agent does this with far fewer tokens, so it fits within free-tier limits.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <a href="#try" className="rounded-xl bg-white px-5 py-2.5 text-sm font-medium text-indigo-700 shadow hover:bg-indigo-50">
              Try it now
            </a>
            <a href="#how" className="rounded-xl px-5 py-2.5 text-sm font-medium text-white ring-1 ring-white/40 hover:bg-white/10">
              How it works
            </a>
          </div>
        </section>

        {/* try it */}
        <section id="try" className="scroll-mt-20 space-y-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Try it</h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Three steps. A run takes 1 to 3 minutes; it runs live, one visitor at a time.
            </p>
          </div>

          <div>
            <StepLabel n={1} title="Pick a request" hint="real tasks from the BFCL benchmark" />
            <div role="radiogroup" aria-label="Request" className="grid gap-3 sm:grid-cols-2">
              {presets.length === 0 &&
                !error &&
                [0, 1, 2, 3].map((i) => <div key={i} className="h-32 animate-pulse rounded-2xl bg-zinc-200/60 dark:bg-zinc-800/60" />)}
              {presets.map((p) => {
                const on = selected === p.id;
                return (
                  <button
                    key={p.id}
                    role="radio"
                    aria-checked={on}
                    onClick={() => setSelected(p.id)}
                    disabled={running}
                    className={`group rounded-2xl border bg-white p-4 text-left shadow-sm transition disabled:opacity-60 dark:bg-zinc-900 ${
                      on
                        ? "border-indigo-500 ring-2 ring-indigo-500/30"
                        : "border-zinc-200 hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`grid size-9 place-items-center rounded-xl ${
                          on ? "bg-indigo-600 text-white" : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                        }`}
                      >
                        <DomainIcon domain={p.domain} className="size-5" />
                      </span>
                      <div>
                        <div className="font-medium">{p.title}</div>
                        <div className="text-xs text-zinc-500">
                          {p.apis.map((a) => APP_NAME[a] ?? a).join(" + ")} · {p.turns.length} request
                          {p.turns.length > 1 ? "s" : ""}
                        </div>
                      </div>
                    </div>
                    <p className="mt-3 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">&ldquo;{p.turns[0]}&rdquo;</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <StepLabel n={2} title="Pick an agent" hint="same AI model, different approach" />
            <div role="radiogroup" aria-label="Agent" className="grid gap-3 sm:grid-cols-2">
              {AGENTS.map((a) => {
                const on = agent === a.kind;
                return (
                  <button
                    key={a.kind}
                    role="radio"
                    aria-checked={on}
                    onClick={() => setAgent(a.kind)}
                    disabled={running}
                    className={`rounded-2xl border bg-white p-4 text-left shadow-sm transition disabled:opacity-60 dark:bg-zinc-900 ${
                      on
                        ? "border-indigo-500 ring-2 ring-indigo-500/30"
                        : "border-zinc-200 hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`size-4 rounded-full border-2 ${on ? "border-indigo-600 bg-indigo-600 shadow-[inset_0_0_0_3px_white] dark:shadow-[inset_0_0_0_3px_#18181b]" : "border-zinc-300 dark:border-zinc-600"}`}
                      />
                      <span className="font-medium">{a.name}</span>
                      {a.tag && (
                        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                          {a.tag}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{a.body}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <StepLabel n={3} title="Run it and watch" />
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={run}
                disabled={!selected || running}
                className="rounded-xl bg-indigo-600 px-6 py-3 font-medium text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50"
              >
                {running ? "Running…" : "Run the agent"}
              </button>
              {running && (
                <button onClick={() => abortRef.current?.abort()} className="text-sm text-zinc-500 underline-offset-4 hover:underline">
                  Stop watching
                </button>
              )}
              {preset && !running && (
                <span className="text-sm text-zinc-500">
                  {preset.title} · {AGENTS.find((a) => a.kind === agent)?.name}
                </span>
              )}
            </div>
          </div>

          {error && (
            <p role="alert" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {error}
            </p>
          )}

          {/* the live run */}
          <section ref={runRef} aria-label="Live run" className="scroll-mt-20" aria-live="polite">
            {events.length > 0 && (
              <div className="space-y-6 rounded-3xl border border-zinc-200 bg-zinc-100/50 p-4 sm:p-6 dark:border-zinc-800 dark:bg-zinc-900/40">
                <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Status" value={running ? "Working…" : done ? "Finished" : "Stopped"} />
                  <Stat label="Steps" value={String(steps.length)} hint="Each step is one message to the AI" />
                  <Stat
                    label="Tokens used"
                    value={tokens.toLocaleString("en-US")}
                    hint="Text sent to and from the AI, in tokens (about 4 characters each)"
                  />
                  <Stat
                    label={totalTools !== undefined ? "Tools shown to the AI" : "Time"}
                    value={shown !== undefined && totalTools !== undefined ? `${shown} of ${totalTools}` : `${elapsed}s`}
                    hint="How many tool descriptions were sent in the latest step"
                  />
                </dl>

                <Trace events={events} running={running} />

                {streamCut && (
                  <p className="text-sm text-zinc-500">The run stopped before finishing (you stopped it, or it hit the time limit).</p>
                )}

                {done?.type === "done" && verdict && (
                  <div
                    className={`animate-rise rounded-2xl border p-5 ${
                      done.success
                        ? "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/50"
                        : "border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`grid size-9 place-items-center rounded-full text-white ${
                          done.success ? "bg-emerald-600" : "bg-rose-600"
                        }`}
                      >
                        {done.success ? <CheckIcon className="size-5" /> : <CrossIcon className="size-5" />}
                      </span>
                      <div>
                        <div className="text-lg font-semibold">{verdict.title}</div>
                        <div className="text-sm opacity-80">Graded by BFCL&apos;s own checker</div>
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed">{verdict.detail}</p>
                    {(done.repairs?.length ?? 0) > 0 && (
                      <p className="mt-2 text-sm">
                        The agent recovered from {done.repairs!.length} mistake{done.repairs!.length > 1 ? "s" : ""} along the way.
                      </p>
                    )}
                    <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Stat label="Messages to the AI" value={String(done.llm_calls)} />
                      <Stat label="Tokens sent" value={done.prompt_tokens.toLocaleString("en-US")} />
                      <Stat label="Tokens received" value={done.completion_tokens.toLocaleString("en-US")} />
                      <Stat label="Time" value={`${done.latency_s}s`} />
                    </dl>
                    <details className="mt-3 text-xs text-zinc-500">
                      <summary className="cursor-pointer">Technical details</summary>
                      <p className="mt-1 break-words font-mono">
                        outcome: {done.outcome}
                        {done.checker.error_message ? ` · grader: ${done.checker.error_message}` : ""}
                        {start?.type === "run_start" ? ` · model: ${start.model}` : ""}
                      </p>
                    </details>
                  </div>
                )}
              </div>
            )}
          </section>
        </section>

        <HowItWorks />
        <WhatIsBfcl />
        <PilotResults />
      </main>

      <footer className="border-t border-zinc-200 py-8 text-sm text-zinc-500 dark:border-zinc-800">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 sm:px-6">
          <span>
            Built on <a className="underline-offset-4 hover:underline" href="https://github.com/huggingface/smolagents" target="_blank" rel="noreferrer">smolagents</a> and{" "}
            <a className="underline-offset-4 hover:underline" href="https://github.com/ShishirPatil/gorilla" target="_blank" rel="noreferrer">BFCL</a>{" "}
            (Apache-2.0). Runs on free tiers; visitor IPs are only stored hashed, for rate limits.
          </span>
          <a className="underline-offset-4 hover:underline" href={GITHUB} target="_blank" rel="noreferrer">Source on GitHub ↗</a>
        </div>
      </footer>
    </>
  );
}
