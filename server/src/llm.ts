// Fluent server — LLM client.
// The Fluent models are plain OpenAI-compatible /v1/chat/completions endpoints
// (deep on 12322, face on 12323). We drive tool-calling ourselves with the
// native OpenAI tool-call format (validated against the running model), so we
// have full control over the parts that get persisted in the SQLite bridge.
//
// Each "turn" runs a round-trip loop: ask the model → if it returns tool_calls,
// execute them and feed the results back as role:"tool" → repeat until the
// model returns a plain text answer.

/** Per-turn context handed to every tool execution (single definition;
 *  tools.ts re-exports it). Without it the tools' per-session guards would
 *  all share one "unknown" key and leak across sessions. */
export interface ToolContext {
  sessionID: string;
  messageID: string;
  dataDir?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  /** JSON Schema for the arguments object. */
  parameters: Record<string, unknown>;
  execute: (args: Record<string, unknown>, ctx?: ToolContext) => Promise<string>;
}

export interface ModelConfig {
  name: string; // internal id, e.g. "deep" / "face"
  baseURL: string; // e.g. "http://127.0.0.1:12321/v1"
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  topK?: number;
  /** Sampling knobs that exist precisely for the failure this project keeps
   *  hitting: a small model, a context full of near-identical exercise blocks,
   *  and a temperature low enough to make "the same again" the most likely
   *  continuation. llama.cpp's own repeat_penalty looks back 64 tokens by
   *  default — the exercise being repeated is two thousand tokens away. These
   *  are sent only when configured, so nothing changes until someone sets them
   *  and measures with scripts/flowed-e2e.py. */
  presencePenalty?: number;
  frequencyPenalty?: number;
  repeatPenalty?: number;
  repeatLastN?: number;
  timeoutMs?: number;
  /** Stream the answer token by token (FLOWED_STREAM=1). Off by default. */
  stream?: boolean;
}

export interface ToolStep {
  kind: "tool";
  callID: string;
  name: string;
  args: Record<string, unknown>;
  output: string;
  status: "completed" | "error";
}

export interface TextStep {
  kind: "text";
  text: string;
}

export type TurnPart = ToolStep | TextStep;

export interface TurnResult {
  text: string;
  /** All parts produced this turn, in order: tool… then the final text. */
  parts: TurnPart[];
  usage?: Record<string, unknown>;
  /** What the turn cost: summed over every round-trip of the tool loop. */
  metrics?: TurnMetrics;
}

export interface TurnMetrics {
  roundtrips: number;
  toolCalls: number;
  /** Which tools were called, in order, with `!` marking a failed one. A count
   *  alone cannot answer "did the tutor record that answer?" — and that is the
   *  question the metrics exist to settle. */
  tools: string[];
  promptTokens: number;
  completionTokens: number;
  /** Wall time spent inside the model calls (excludes tool execution). */
  modelMs: number;
}

interface ChatMessage {
  role: string;
  content: string | null;
  tool_calls?: unknown;
  tool_call_id?: string;
}

interface OpenAIResponse {
  choices: Array<{
    finish_reason: string;
    message: {
      role: string;
      content: string | null;
      tool_calls?: Array<{
        id: string;
        type: string;
        function: { name: string; arguments: string };
      }>;
    };
  }>;
  usage?: Record<string, unknown>;
}

// ---- streaming ------------------------------------------------------------
// llama.cpp streams OpenAI-style SSE: one `data:` line per chunk, each with a
// `delta`. Text deltas go straight to the UI; tool_calls arrive FRAGMENTED
// (name and arguments in pieces, addressed by `index`) and must be reassembled
// before anything can be executed. The accumulator below rebuilds the exact
// same shape a non-streaming answer has, so runTurn's loop stays untouched.

export interface StreamAccumulator {
  content: string;
  toolCalls: Map<number, { id: string; type: string; function: { name: string; arguments: string } }>;
  finishReason: string;
  usage?: Record<string, unknown>;
}

export function newStreamAccumulator(): StreamAccumulator {
  return { content: "", toolCalls: new Map(), finishReason: "" };
}

/** Apply one SSE payload. Returns the text delta it carried (may be ""). */
export function applyStreamChunk(acc: StreamAccumulator, payload: string): string {
  const body = payload.trim();
  if (!body || body === "[DONE]") return "";
  let json: any;
  try {
    json = JSON.parse(body);
  } catch {
    return ""; // a partial or non-JSON line: ignore, never throw mid-stream
  }
  if (json.usage) acc.usage = json.usage as Record<string, unknown>;
  const choice = json.choices?.[0];
  if (!choice) return "";
  if (choice.finish_reason) acc.finishReason = String(choice.finish_reason);
  const delta = choice.delta ?? {};
  let emitted = "";
  if (typeof delta.content === "string" && delta.content.length) {
    acc.content += delta.content;
    emitted = delta.content;
  }
  for (const raw of delta.tool_calls ?? []) {
    const idx = typeof raw.index === "number" ? raw.index : 0;
    const cur =
      acc.toolCalls.get(idx) ?? { id: "", type: "function", function: { name: "", arguments: "" } };
    if (raw.id) cur.id = String(raw.id);
    if (raw.type) cur.type = String(raw.type);
    if (raw.function?.name) cur.function.name += String(raw.function.name);
    if (typeof raw.function?.arguments === "string") cur.function.arguments += raw.function.arguments;
    acc.toolCalls.set(idx, cur);
  }
  return emitted;
}

/** Rebuild the non-streaming response shape from the accumulator. */
export function finishStream(acc: StreamAccumulator): OpenAIResponse {
  const toolCalls = [...acc.toolCalls.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([idx, tc]) => ({
      id: tc.id || `call_${idx}`,
      type: tc.type || "function",
      function: { name: tc.function.name, arguments: tc.function.arguments },
    }));
  const finish = acc.finishReason || (toolCalls.length ? "tool_calls" : "stop");
  return {
    choices: [
      {
        finish_reason: finish,
        message: {
          role: "assistant",
          content: acc.content.length ? acc.content : null,
          ...(toolCalls.length ? { tool_calls: toolCalls } : {}),
        },
      },
    ],
    usage: acc.usage,
  };
}

/**
 * Some chat templates accept a system message only at the start (Qwen3.5 and
 * others: "TemplateError: System message must be at the beginning."). The
 * server puts per-turn notes (pacing, retry) as a system message at the END of
 * the history — right where a small model reads them — and Qwen3-14B's template
 * accepts that. For a template that refuses it, the same notes go in the last
 * user turn instead, marked as not written by the learner. Leading system
 * messages are merged into one. Measured 2026-09-27: a 27B behind TabbyAPI
 * answered every exercise with HTTP 400.
 */
export function foldLateSystem(messages: ChatMessage[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  let head = true;
  for (const m of messages) {
    if (m.role === "system") {
      if (head) {
        const first = out[0];
        if (first) out[0] = { ...first, content: `${first.content ?? ""}\n\n${m.content ?? ""}` };
        else out.push({ ...m });
        continue;
      }
      const note = `[Note for the tutor — not written by the learner]\n${m.content ?? ""}`;
      const prev = out[out.length - 1];
      if (prev && prev.role === "user") out[out.length - 1] = { ...prev, content: `${prev.content ?? ""}\n\n${note}` };
      else out.push({ role: "user", content: note });
      continue;
    }
    head = false;
    out.push(m);
  }
  return out;
}

/** The template's own words for "no system message here". */
export const LATE_SYSTEM_REFUSED = /system message must be at the beginning|roles must alternate/i;

/** Endpoints (baseURL) that refused a late system message once: folded from then
 *  on, for the life of the process, so the refusal costs one request, not one per turn. */
const foldsSystem = new Set<string>();

async function chatStreaming(
  cfg: ModelConfig,
  messages: ChatMessage[],
  tools: ToolDefinition[],
  onDelta: (text: string) => void
): Promise<OpenAIResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), cfg.timeoutMs ?? 600000);
  try {
    const res = await fetch(`${cfg.baseURL}/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: cfg.name,
        messages,
        tools: tools.map((t) => ({
          type: "function",
          function: { name: t.name, description: t.description, parameters: t.parameters },
        })),
        tool_choice: "auto",
        temperature: cfg.temperature ?? 0.7,
        max_tokens: cfg.maxTokens ?? 4096,
        top_p: cfg.topP ?? 0.95,
        ...(cfg.topK !== undefined ? { top_k: cfg.topK } : {}),
        ...(cfg.presencePenalty !== undefined ? { presence_penalty: cfg.presencePenalty } : {}),
        ...(cfg.frequencyPenalty !== undefined ? { frequency_penalty: cfg.frequencyPenalty } : {}),
        ...(cfg.repeatPenalty !== undefined ? { repeat_penalty: cfg.repeatPenalty } : {}),
        ...(cfg.repeatLastN !== undefined ? { repeat_last_n: cfg.repeatLastN } : {}),
        stream: true,
        stream_options: { include_usage: true },
      }),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => "");
      throw new Error(`LLM HTTP ${res.status}: ${body.slice(0, 300)}`);
    }
    const acc = newStreamAccumulator();
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line.startsWith("data:")) continue;
        const delta = applyStreamChunk(acc, line.slice(5));
        if (delta) onDelta(delta);
      }
    }
    if (buffer.trim().startsWith("data:")) {
      const delta = applyStreamChunk(acc, buffer.trim().slice(5));
      if (delta) onDelta(delta);
    }
    return finishStream(acc);
  } finally {
    clearTimeout(timeout);
  }
}

async function chat(
  cfg: ModelConfig,
  messages: ChatMessage[],
  tools: ToolDefinition[],
  signal?: AbortSignal
): Promise<OpenAIResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), cfg.timeoutMs ?? 600000);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);
  try {
    const res = await fetch(`${cfg.baseURL}/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: cfg.name,
        messages,
        tools: tools.map((t) => ({
          type: "function",
          function: {
            name: t.name,
            description: t.description,
            parameters: t.parameters,
          },
        })),
        tool_choice: "auto",
        temperature: cfg.temperature ?? 0.7,
        max_tokens: cfg.maxTokens ?? 4096,
        top_p: cfg.topP ?? 0.95,
        ...(cfg.topK !== undefined ? { top_k: cfg.topK } : {}),
        ...(cfg.presencePenalty !== undefined ? { presence_penalty: cfg.presencePenalty } : {}),
        ...(cfg.frequencyPenalty !== undefined ? { frequency_penalty: cfg.frequencyPenalty } : {}),
        ...(cfg.repeatPenalty !== undefined ? { repeat_penalty: cfg.repeatPenalty } : {}),
        ...(cfg.repeatLastN !== undefined ? { repeat_last_n: cfg.repeatLastN } : {}),
        stream: false,
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`LLM HTTP ${res.status}: ${body.slice(0, 300)}`);
    }
    return (await res.json()) as OpenAIResponse;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", onAbort);
  }
}

/**
 * Run one agent turn: round-trip loop with tool execution.
 * @param cfg   model connection config
 * @param system system prompt (or null)
 * @param history prior messages (OpenAI format) INCLUDING the latest user turn
 * @param tools available tools
 * @param maxRoundtrips max number of tool round-trips before giving up
 * @param ctx    per-turn context (session/message id) passed to every tool
 * @param onDelta called with each text fragment when cfg.stream is on
 */
export async function runTurn(
  cfg: ModelConfig,
  system: string | null,
  history: ChatMessage[],
  tools: ToolDefinition[],
  maxRoundtrips = 6,
  onPart?: (step: TurnPart) => void,
  ctx?: ToolContext,
  onDelta?: (text: string) => void
): Promise<TurnResult> {
  const messages: ChatMessage[] = [];
  if (system) messages.push({ role: "system", content: system });
  messages.push(...history);

  const parts: TurnPart[] = [];
  const metrics: TurnMetrics = {
    roundtrips: 0,
    toolCalls: 0,
    tools: [],
    promptTokens: 0,
    completionTokens: 0,
    modelMs: 0,
  };
  const countUsage = (usage: Record<string, unknown> | undefined) => {
    const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
    metrics.promptTokens += n(usage?.prompt_tokens);
    metrics.completionTokens += n(usage?.completion_tokens);
  };
  let lastText = "";
  const push = (step: TurnPart) => {
    parts.push(step);
    onPart?.(step);
  };

  for (let i = 0; i < maxRoundtrips; i++) {
    const startedAt = Date.now();
    // Streaming is opt-in (FLOWED_STREAM=1) and degrades to a normal call: if
    // the endpoint refuses to stream, the error propagates to agent.ts, which
    // already knows how to fall back.
    const send = (msgs: ChatMessage[]) =>
      cfg.stream && onDelta ? chatStreaming(cfg, msgs, tools, onDelta) : chat(cfg, msgs, tools);
    let resp: OpenAIResponse;
    if (foldsSystem.has(cfg.baseURL)) {
      resp = await send(foldLateSystem(messages));
    } else {
      try {
        resp = await send(messages);
      } catch (e) {
        if (!LATE_SYSTEM_REFUSED.test(String(e))) throw e;
        foldsSystem.add(cfg.baseURL);
        console.log(`[Flowed] ${cfg.baseURL}: the chat template refuses late system messages — folding them into the user turn from now on`);
        resp = await send(foldLateSystem(messages));
      }
    }
    metrics.modelMs += Date.now() - startedAt;
    metrics.roundtrips += 1;
    countUsage(resp.usage);
    const choice = resp.choices[0];
    if (!choice) {
      // No choices returned: treat as an empty assistant text and stop.
      push({ kind: "text", text: "" });
      return { text: "", parts, metrics };
    }
    const msg = choice.message;

    // Persist-friendly snapshot of the assistant's raw tool_calls.
    const tcs = (msg.tool_calls ?? []).map((tc) => ({
      id: tc.id,
      type: tc.type,
      function: { name: tc.function.name, arguments: tc.function.arguments },
    }));

    if (choice.finish_reason === "tool_calls" && tcs.length) {
      messages.push({ role: "assistant", content: msg.content ?? null, tool_calls: tcs });

      for (const tc of tcs) {
        const tool = tools.find((t) => t.name === tc.function.name);
        if (!tool) {
          push({
            kind: "tool",
            callID: tc.id,
            name: tc.function.name,
            args: {},
            output: `[unknown tool: ${tc.function.name}]`,
            status: "error",
          });
          messages.push({ role: "tool", tool_call_id: tc.id, content: `[unknown tool: ${tc.function.name}]` });
          continue;
        }
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(tc.function.arguments || "{}");
        } catch {
          args = {};
        }
        let output: string;
        let status: "completed" | "error" = "completed";
        try {
          output = await tool.execute(args, ctx);
        } catch (e) {
          output = `[tool error: ${e instanceof Error ? e.message : String(e)}]`;
          status = "error";
        }
        metrics.toolCalls += 1;
        // A tool that answers "REJECTED: …" ran fine and refused — from the
        // outside that is indistinguishable from success, and it is exactly
        // the case worth seeing in the log.
        const refused = status === "error" || /^REJECTED\b/.test(output);
        metrics.tools.push(refused ? `!${tc.function.name}` : tc.function.name);
        push({ kind: "tool", callID: tc.id, name: tc.function.name, args, output, status });
        messages.push({ role: "tool", tool_call_id: tc.id, content: output });
      }

      // If model also produced text during this assistant turn, keep it as fallback.
      if (msg.content) lastText = msg.content;
      continue;
    }

    const text = msg.content ?? "";
    push({ kind: "text", text });
    return {
      text,
      parts,
      usage: (resp.usage ?? undefined) as Record<string, unknown> | undefined,
      metrics,
    };
  }

  // Loop exhausted without a text answer: return the last part seen.
  push({ kind: "text", text: lastText });
  return { text: lastText, parts, metrics };
}
