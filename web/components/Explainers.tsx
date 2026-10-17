import { CheckIcon, StackIcon, ToolIcon } from "@/components/icons";

const card = "rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900";

export function HowItWorks() {
  const steps = [
    {
      title: "You give it a request",
      body: "Like “unlock my car and turn on the headlights”. Some tasks have several requests in a row, like a real conversation.",
    },
    {
      title: "The AI uses tools",
      body: "A tool is a function it can call, like lockDoors or get_stock_info. The tools belong to pretend apps that run safely on the server.",
    },
    {
      title: "Each step costs tokens",
      body: "Tokens are chunks of text (about 4 characters each). Free AI services limit how many you can send per minute and per day.",
    },
    {
      title: "A grader checks the result",
      body: "It doesn't read the AI's reply. It checks whether the apps ended up in exactly the right state.",
    },
  ];
  return (
    <section id="how" className="scroll-mt-20">
      <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
      <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((s, i) => (
          <li key={s.title} className={card}>
            <div className="grid size-8 place-items-center rounded-full bg-indigo-600 text-sm font-semibold text-white">
              {i + 1}
            </div>
            <h3 className="mt-3 font-medium">{s.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{s.body}</p>
          </li>
        ))}
      </ol>

      <div className={`${card} mt-4`}>
        <h3 className="font-medium">What makes the lean agent different</h3>
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          <div>
            <div className="text-sm font-medium text-zinc-500">Standard agent: every message carries every tool&apos;s manual</div>
            <div className="mt-2 flex flex-wrap gap-1" aria-hidden>
              {Array.from({ length: 28 }, (_, i) => (
                <span key={i} className="h-3 w-5 rounded-sm bg-zinc-300 dark:bg-zinc-700" />
              ))}
            </div>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              About 28 tools, described twice, plus the whole history, on every step. Long tasks outgrow the free
              tier&apos;s size limit.
            </p>
          </div>
          <div>
            <div className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Lean agent: only the tools it needs right now</div>
            <div className="mt-2 flex flex-wrap gap-1" aria-hidden>
              {Array.from({ length: 6 }, (_, i) => (
                <span key={i} className="h-3 w-5 rounded-sm bg-indigo-500" />
              ))}
            </div>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              It picks the few relevant tools each step, describes them once and trims old history. When the AI
              makes a mistake, like calling a tool that doesn&apos;t exist, it gets told how to fix it instead of
              crashing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

export function WhatIsBfcl() {
  const facts = [
    { icon: <StackIcon className="size-4" />, text: "200 multi-step tasks, written by researchers" },
    { icon: <ToolIcon className="size-4" />, text: "Pretend apps: files, stocks, a car, travel, messaging and more" },
    { icon: <CheckIcon className="size-4" />, text: "Graded by the apps' final state, not by how the reply sounds" },
  ];
  return (
    <section id="bfcl" className="scroll-mt-20">
      <h2 className="text-2xl font-semibold tracking-tight">What is BFCL?</h2>
      <div className={`${card} mt-5`}>
        <p className="leading-relaxed">
          <strong>BFCL</strong> (the Berkeley Function Calling Leaderboard) is a public test from UC Berkeley that
          measures how well AI models use tools. Its <em>multi-turn</em> tasks hand the AI a set of pretend apps and a
          conversation of requests, for example: move a file into a new folder, then search it, then share it.
        </p>
        <p className="mt-3 leading-relaxed text-zinc-600 dark:text-zinc-400">
          Grading is strict and automatic. BFCL replays everything the agent did, then checks that each app ended up
          exactly where the correct solution leaves it. Saying the right thing isn&apos;t enough: the car must really
          be unlocked, the right amount really deposited. This demo uses BFCL&apos;s own grader, unchanged.
        </p>
        <ul className="mt-5 grid gap-3 sm:grid-cols-3">
          {facts.map((f) => (
            <li key={f.text} className="flex gap-2 rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-950">
              <span className="mt-0.5 text-indigo-600 dark:text-indigo-400">{f.icon}</span>
              {f.text}
            </li>
          ))}
        </ul>
        <a
          className="mt-4 inline-block text-sm text-indigo-600 underline-offset-4 hover:underline dark:text-indigo-400"
          href="https://gorilla.cs.berkeley.edu/leaderboard.html"
          target="_blank"
          rel="noreferrer"
        >
          See the official leaderboard ↗
        </a>
      </div>
    </section>
  );
}

// Numbers from eval/results/pilot (gpt-oss-120b, the same 10 BFCL tasks for both agents).
const PILOT = [
  { name: "Standard agent", passed: 1, tokensPerStep: 5345, tone: "bg-zinc-400 dark:bg-zinc-600" },
  { name: "Lean agent (tool retrieval)", passed: 6, tokensPerStep: 1956, tone: "bg-indigo-500" },
];

export function PilotResults() {
  const maxTokens = Math.max(...PILOT.map((p) => p.tokensPerStep));
  return (
    <section id="results" className="scroll-mt-20">
      <h2 className="text-2xl font-semibold tracking-tight">Early results</h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        A pilot on 10 BFCL tasks with the same AI model (gpt-oss-120b). It is a small sample; the full evaluation is
        in progress.
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className={card}>
          <h3 className="text-sm font-medium text-zinc-500">Tasks passed (out of 10)</h3>
          <div className="mt-4 space-y-3">
            {PILOT.map((p) => (
              <div key={p.name}>
                <div className="flex justify-between text-sm">
                  <span>{p.name}</span>
                  <span className="font-semibold">{p.passed} / 10</span>
                </div>
                <div className="mt-1 h-2.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <div className={`h-full rounded-full ${p.tone}`} style={{ width: `${p.passed * 10}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className={card}>
          <h3 className="text-sm font-medium text-zinc-500">Tokens sent per step (lower is cheaper)</h3>
          <div className="mt-4 space-y-3">
            {PILOT.map((p) => (
              <div key={p.name}>
                <div className="flex justify-between text-sm">
                  <span>{p.name}</span>
                  <span className="font-semibold">{p.tokensPerStep.toLocaleString("en-US")}</span>
                </div>
                <div className="mt-1 h-2.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <div
                    className={`h-full rounded-full ${p.tone}`}
                    style={{ width: `${(p.tokensPerStep / maxTokens) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            {Math.round((1 - PILOT[1].tokensPerStep / PILOT[0].tokensPerStep) * 100)}% fewer tokens per step. Of the
            standard agent&apos;s 9 failures, 4 were messages too big for the free tier and 4 were invalid tool calls
            the AI service rejected.
          </p>
        </div>
      </div>
    </section>
  );
}
