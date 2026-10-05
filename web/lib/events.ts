// Trace events streamed by POST /api/run (one JSON object per line). Mirrors agent/runner.py.

export type Preset = {
  id: string;
  title: string;
  domain: string;
  apis: string[];
  turns: string[];
};

export type RunEvent =
  | { type: "run_start"; task_id: string; model: string; turns: number; tools: number }
  | { type: "turn_start"; turn: number; user: string }
  | { type: "tool_call"; turn: number; name: string; args: Record<string, unknown> | string }
  | { type: "tool_result"; turn: number; name: string; observation: string }
  | {
      type: "step";
      turn: number;
      step: number;
      prompt_tokens: number;
      completion_tokens: number;
      duration_s: number | null;
      error: string | null;
    }
  | { type: "turn_end"; turn: number; answer: string }
  | { type: "run_error"; kind: string; message: string }
  | {
      type: "done";
      task_id: string;
      success: boolean;
      outcome: string;
      checker: { valid: boolean; error_type?: string; error_message?: string };
      latency_s: number;
      llm_calls: number;
      prompt_tokens: number;
      completion_tokens: number;
      calls: string[][][];
    };

/** POST /api/run and call onEvent for each NDJSON line as it arrives. */
export async function streamRun(
  taskId: string,
  onEvent: (e: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    let message = `Request failed (${resp.status})`;
    try {
      message = (await resp.json()).error ?? message;
    } catch {}
    throw new Error(message);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line) as RunEvent);
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as RunEvent);
}
