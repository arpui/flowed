// Fluent server — the agent orchestrator.
// Runs a "turn" (a /fluent-* command or a learner chat message) over the LLM,
// persists every produced part into the SQLite bridge, and emits SSE events so
// the web UI renders incrementally (same contract opencode exposed).

import fs from "node:fs";
import path from "node:path";
import type { FluentDB, SessionRow, MessageRow } from "./db";
import { runTurn, type ToolDefinition, type TurnPart, type ModelConfig, type ToolStep, type TurnMetrics } from "./llm";
import { buildTools, type DeepEvaluator } from "./tools";
import { loadCommand } from "./commands";
import {
  resolveSessionTarget,
  resolveStopMode,
  isPaced,
  wrapUpNote,
  countGradedInText,
  lessonTarget,
  lessonSkillSlot,
  skillDebts,
  exerciseFingerprints,
  pruneHistory,
  historyBudget,
  estimateTokens,
  dailyFace,
  resolveDailyGoal,
  resolveReviewGate,
  reviewGateNote,
  NO_GATE,
  type ReviewGate,
} from "./pacing";
import {
  readDaily,
  bumpDaily,
  readTally,
  creditLesson,
  readPlan,
  writePlan,
  today as todayISO,
  type LessonPlan,
} from "./daily";

export interface SSEEvent {
  type: string;
  properties: Record<string, unknown>;
}

export interface TurnOutcome {
  info: Record<string, unknown>;
  parts: Record<string, unknown>[];
}

const AGENT_FILES: Record<string, string> = {
  learner: "learner.md",
  tutor: "tutor.md",
  "tutor-fast": "tutor-fast.md",
};

// Model per agent id (matches the routing in docs/dual-model).
export function modelForAgent(agent: string, models: Models): ModelConfig {
  if (agent === "tutor-fast") return models.face;
  return models.deep;
}

// Face→deep fallback: el face (12323) és una descàrrega opcional per velocitat.
// Si no respon, el tutor-fast corre amb el deep (12322) sense que l'usuari perdi
// res — només queda una línia al log del servidor (cap avís al xat).
async function faceHealthy(baseURL: string): Promise<boolean> {
  try {
    const origin = new URL(baseURL).origin;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2000);
    let ok = false;
    try {
      const res = await fetch(origin + "/health", { signal: ctrl.signal });
      ok = res.ok;
    } finally {
      clearTimeout(t);
    }
    return ok;
  } catch {
    return false;
  }
}

function isConnError(e: unknown): boolean {
  const m = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
  return /ECONNREFUSED|ENOTFOUND|fetch failed|failed to fetch|socket hang up|network|aborted/i.test(m);
}

export async function resolveModel(
  agent: string,
  models: Models
): Promise<{ model: ModelConfig; fellBack: boolean }> {
  const primary = modelForAgent(agent, models);
  if (agent !== "tutor-fast" || primary.name !== "face") return { model: primary, fellBack: false };
  if (await faceHealthy(primary.baseURL)) return { model: primary, fellBack: false };
  console.log(`[Fluent] face (${primary.baseURL}) no disponible → tutor-fast amb deep (${models.deep.baseURL})`);
  return { model: models.deep, fellBack: true };
}

export interface Models {
  deep: ModelConfig;
  face: ModelConfig;
}

interface TurnKind {
  kind: "message";
  text: string;
  agentArg: string;
}
// kind "command" is created by the caller and passed as the first user turn.

export class Agent {
  private db: FluentDB;
  private root: string;
  private dataDirFn: () => string;
  private models: Models;
  private deep: DeepEvaluator;
  private tools: ReturnType<typeof buildTools>;
  private emit: (e: SSEEvent) => void;
  private lastDailyBackup = "";
  /** Sessions already told to wrap up — the nudge is given once. */
  private wrappedUp = new Set<string>();
  /** The command a session opened with. Decides whether the review gate
   *  applies: starting straight into 📝/🗣️/📚/📖 is the learner saying what
   *  they want today, and that is allowed — once, at the start. */
  private sessionOpenedWith = new Map<string, string>();
  /** The practice mode a session is in right now (last command pressed). */
  private currentCommand = new Map<string, string>();

  constructor(opts: {
    db: FluentDB;
    root: string;
    dataDir: () => string;
    models: Models;
    deep: DeepEvaluator;
    emit: (e: SSEEvent) => void;
  }) {
    this.db = opts.db;
    this.root = opts.root;
    this.dataDirFn = opts.dataDir;
    this.models = opts.models;
    this.deep = opts.deep;
    this.emit = opts.emit;
    this.tools = buildTools({ root: opts.root, dataDir: opts.dataDir, deep: opts.deep });
  }

  private dataDir() {
    return this.dataDirFn();
  }

  /** The deep model's context window, from config. */
  private contextTokens(): number {
    const n = Number(process.env.FLUENT_DEEP_CTX);
    if (Number.isFinite(n) && n > 0) return n;
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(this.root, "config", "fluent.json"), "utf8"));
      const ctx = Number(cfg?.models?.deep?.ctx);
      if (Number.isFinite(ctx) && ctx > 0) return ctx;
    } catch {
      /* fall through */
    }
    return 32768;
  }

  private maxOutputTokens(): number {
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(this.root, "config", "fluent.json"), "utf8"));
      const n = Number(cfg?.models?.deep?.max_tokens);
      if (Number.isFinite(n) && n > 0) return n;
    } catch {
      /* default below */
    }
    return 4096;
  }

  // ---- system prompt -------------------------------------------------------

  private readRuleFile(filename: string): string {
    const p = path.join(this.root, filename);
    try {
      return fs.readFileSync(p, "utf8");
    } catch {
      return "";
    }
  }

  private readAgentBody(agent: string): string {
    const file = AGENT_FILES[agent] ?? "learner.md";
    const p = path.join(this.root, "prompts", "agents", file);
    try {
      const raw = fs.readFileSync(p, "utf8");
      return raw.startsWith("---") ? raw.slice(raw.indexOf("\n---", 4) + 4) : raw;
    } catch {
      return "";
    }
  }

  private buildSystemPrompt(agent: string): string {
    const blocks: string[] = [];
    for (const f of ["AGENTS.md", "LEARNING_SYSTEM.md"]) {
      const c = this.readRuleFile(f);
      if (c.trim()) blocks.push(`Instructions from: ${path.join(this.root, f)}\n\n${c.trim()}`);
    }
    const body = this.readAgentBody(agent).trim();
    if (body) blocks.push(body);
    // Shared behavioral rules: single source concatenated into EVERY agent
    // (rollback = delete these 3 lines; agent files keep their legacy copies).
    const shared = this.readRuleFile(path.join("prompts", "agents", "rules.md")).trim();
    if (shared) blocks.push(`Shared behavioral rules (apply on top of everything above):\n\n${shared}`);
    return blocks.join("\n\n");
  }

  // ---- history reconstruction ----------------------------------------------

  private historyToMessages(sessionId: string): ChatMsg[] {
    const messages = this.db.getMessages(sessionId);
    const out: ChatMsg[] = [];
    for (const m of messages) {
      const role = String(m.data["role"] ?? "assistant");
      const parts = this.db.getParts(m.id);
      if (role === "user") {
        const text = parts
          .filter((p) => (p.data["type"] as string) === "text")
          .map((p) => String(p.data["text"] ?? ""))
          .join("\n");
        if (text.trim()) out.push({ role: "user", content: text });
        continue;
      }
      // assistant: group tool parts, then the final text part.
      const toolParts = parts.filter((p) => (p.data["type"] as string) === "tool");
      const textParts = parts.filter((p) => (p.data["type"] as string) === "text");
      if (toolParts.length) {
        const tcs = toolParts.map((p) => {
          const state = p.data["state"] as { input?: unknown; output?: unknown } | undefined;
          return {
            id: String(p.data["callID"] ?? ""),
            type: "function",
            function: {
              name: String(p.data["tool"] ?? ""),
              arguments: JSON.stringify(state?.input ?? {}),
            },
          };
        });
        out.push({ role: "assistant", content: null, tool_calls: tcs });
        for (const p of toolParts) {
          const state = p.data["state"] as { output?: unknown } | undefined;
          out.push({
            role: "tool",
            tool_call_id: String(p.data["callID"] ?? ""),
            content: String(state?.output ?? ""),
          });
        }
      }
      const finalText = textParts.map((p) => String(p.data["text"] ?? "")).join("\n").trim();
      out.push({ role: "assistant", content: finalText });
    }
    return out;
  }

  // ---- persistence ---------------------------------------------------------

  private persistUserTurn(sessionId: string, text: string, agent: string, isCommand: boolean): MessageRow {
    const msg = this.db.insertMessage(sessionId, {
      role: "user",
      time: { created: Date.now() },
      agent,
      model: { providerID: "fluent-deep", modelID: "deep" },
      summary: { diffs: [] },
    });
    this.db.insertPart(msg.id, sessionId, { type: "text", text });
    // SSE: confirm the user message (chip or plain bubble).
    this.emit({
      type: "message.updated",
      properties: { info: this.db.getMessageView(msg).info },
    });
    return msg;
  }

  private createAssistantMessage(sessionId: string, agent: string, model: ModelConfig): MessageRow {
    const msg = this.db.insertMessage(sessionId, {
      parentID: null,
      role: "assistant",
      agent,
      model: { providerID: model.name === "deep" ? "fluent-deep" : "llama-face", modelID: model.name },
      cost: 0,
      tokens: { total: 0 },
    });
    // Emit before any part so the UI creates the message + "pensant…" placeholder.
    this.emit({ type: "message.updated", properties: { info: this.db.getMessageView(msg).info } });
    return msg;
  }

  // True once the tutor has produced any text in this session (i.e. this
  // command continues, rather than starts, the practice). Best-effort.
  private sessionHasAssistantText(sessionId: string): boolean {
    try {
      for (const m of this.db.getMessages(sessionId)) {
        if (String(m.data["role"] ?? "assistant") !== "assistant") continue;
        for (const p of this.db.getParts(m.id)) {
          const d = p.data as Record<string, unknown>;
          if (d["type"] === "text" && String(d["text"] ?? "").trim()) return true;
        }
      }
    } catch {
      /* best-effort; never break the turn */
    }
    return false;
  }

  // ---- turn drivers --------------------------------------------------------

  async runCommand(sessionId: string, commandName: string, agentArg: string): Promise<TurnOutcome> {
    const dataDir = this.dataDir();
    if (!this.sessionOpenedWith.has(sessionId)) {
      this.sessionOpenedWith.set(sessionId, commandName);
      if (this.sessionOpenedWith.size > 500) this.sessionOpenedWith.clear();
    }
    // Which practice the learner is in right now — the Lesson credits only
    // answers given inside it.
    this.currentCommand.set(sessionId, commandName);
    if (this.currentCommand.size > 500) this.currentCommand.clear();
    // Second and later commands of a session do not need the state block again:
    // it is already in the history, and re-running the directive would re-inject
    // several KB of JSON per command.
    const continuing = this.sessionHasAssistantText(sessionId);
    const resolved = await loadCommand(commandName, {
      root: this.root,
      dataDir,
      env: { ...process.env as Record<string, string> },
      skipDirectives: continuing,
    });
    if (!resolved) {
      throw new Error(`unknown command: ${commandName}`);
    }
    const agent = resolved.agent; // frontmatter wins (tutor / tutor-fast)
    // Continuing session (not a fresh start): mark it ON the recorded turn so
    // the model continues instead of re-greeting (prompt rules alone lose to
    // the greeting template). Skipped for fluent-end (own finalization flow).
    let body = resolved.body;
    if (commandName !== "fluent-end" && continuing) {
      body += "\n\n(Continuing session: the history above already contains tutor turns. Do NOT greet, do NOT show the practice menu — continue the ongoing practice directly: evaluate any pending answer, otherwise present the next exercise.)";
    }
    this.persistUserTurn(sessionId, body, agent, true);
    const system = this.buildSystemPrompt(agent);
    const history = this.historyToMessages(sessionId);
    const outcome = await this.executeTurn(sessionId, agent, system, history, this.tools.definitions);

    // Auto-run fluent-db-updater for fluent-end command to finalize Capa B
    if (commandName === "fluent-end") {
      await this.runDbUpdater(sessionId, dataDir);
    }

    return outcome;
  }

  async runMessage(sessionId: string, text: string, agentArg: string): Promise<TurnOutcome> {
    const agent = agentArg || "learner";
    this.persistUserTurn(sessionId, text, agent, false);
    const system = this.buildSystemPrompt(agent);
    return this.executeTurn(sessionId, agent, system, this.historyToMessages(sessionId), this.tools.definitions);
  }

  private async executeTurn(
    sessionId: string,
    agent: string,
    system: string,
    history: ChatMsg[],
    tools: ToolDefinition[]
  ): Promise<TurnOutcome> {
    // Update activity timestamp at start of turn to prevent sweeper from
    // marking session stale during long model processing (deep model on large contexts).
    this.db.touchSession(sessionId);
    // A session the learner comes back to is not finished, whatever the
    // sweeper decided 30 minutes ago.
    try {
      if (this.db.reopenIfFinalized(sessionId)) {
        // The sweeper reads its own copy of the flag from session-draft.json;
        // clearing only the database one would leave it skipping this session.
        const draftPath = path.join(this.dataDir(), "session-draft.json");
        try {
          const draft = JSON.parse(fs.readFileSync(draftPath, "utf8"));
          if (draft.capa_b_sid === sessionId || draft.session_id === sessionId) {
            delete draft.capa_b_done;
            fs.writeFileSync(draftPath, JSON.stringify(draft, null, 2));
          }
        } catch {
          /* no draft yet */
        }
        console.log(`[Fluent] ↩ session ${sessionId} reopened — Capa B will run again at the end`);
      }
    } catch {
      /* best-effort: never block a turn over bookkeeping */
    }

    // Pacing: appended to what the model sees, never persisted into the
    // learner's own message.
    const note = this.pacingNote(sessionId);

    // Keep the request inside the model's context. Without this the turn fails
    // outright — seen live: 41808 tokens against a 40960 window — and the
    // learner gets an error instead of an exercise. Safe to do now that the
    // server, not the history, remembers what has already been asked.
    const budget = historyBudget(
      this.contextTokens(),
      estimateTokens(system) + estimateTokens(note ?? ""),
      this.maxOutputTokens()
    );
    const pruned = pruneHistory(history, budget);
    if (pruned.dropped) {
      console.log(
        `[Fluent] ✂ session ${sessionId}: dropped ${pruned.dropped} old message(s) to fit the context ` +
          `(history ≈${pruned.estimatedTokens} tok, budget ${budget})`
      );
    }
    history = pruned.messages;

    if (note) history = [...history, { role: "system", content: note }];

    const { model } = await resolveModel(agent, this.models);
    const msg = this.createAssistantMessage(sessionId, agent, model);
    const view = () => this.db.getMessageView(msg);

    // Streaming (FLUENT_STREAM=1): the first delta creates an empty text part,
    // the rest arrive as message.part.delta events — the shape web/app.js
    // already knows. The part row is written once, when the segment closes, so
    // the transcript on disk matches what the learner saw without one SQLite
    // write per token.
    let streamPartId: string | null = null;
    let streamText = "";
    const emitPart = (partId: string) => {
      const part = view().parts.find((p) => p.id === partId) ?? view().parts.at(-1);
      this.emit({ type: "message.part.updated", properties: { part } });
    };
    const flushStream = () => {
      if (!streamPartId) return;
      this.db.updatePart(streamPartId, { type: "text", text: streamText });
      const id = streamPartId;
      streamPartId = null;
      streamText = "";
      emitPart(id);
    };
    const onDelta = (text: string) => {
      if (!streamPartId) {
        streamPartId = this.db.insertPart(msg.id, sessionId, { type: "text", text: "" }).id;
        streamText = "";
        emitPart(streamPartId);
      }
      streamText += text;
      this.emit({
        type: "message.part.delta",
        properties: {
          sessionID: sessionId,
          messageID: msg.id,
          partID: streamPartId,
          field: "text",
          delta: text,
        },
      });
    };

    // Persist + emit each part as soon as it is produced, so the UI streams it.
    const onPart = (step: TurnPart) => {
      if (step.kind === "tool") {
        flushStream(); // close any text the model streamed before calling a tool
        const t = step as ToolStep;
        const part = this.db.insertPart(msg.id, sessionId, {
          type: "tool",
          tool: t.name,
          callID: t.callID,
          state: { status: t.status, input: t.args, output: t.output },
        });
        emitPart(part.id);
        return;
      }
      if (streamPartId) {
        // Same segment the learner just watched arrive: close it with the
        // final text instead of appending a duplicate part.
        streamText = step.text;
        flushStream();
        return;
      }
      const part = this.db.insertPart(msg.id, sessionId, { type: "text", text: step.text });
      emitPart(part.id);
    };

    const startedAt = Date.now();
    let metrics: TurnMetrics | undefined;
    try {
      const result = await runTurn(
        model, system, history, tools, 6, onPart,
        { sessionID: sessionId, messageID: msg.id, dataDir: this.dataDir() },
        onDelta
      );
      metrics = result.metrics;
    } catch (e) {
      // El face pot caure a mig torn: un sol reintent amb deep abans de rendir-se.
      if (model.name !== "deep" && isConnError(e)) {
        console.log(`[Fluent] face cau a mig torn (${model.baseURL}) → reintent amb deep`);
        try {
          flushStream(); // whatever the face managed to stream stays on disk
          const retry = await runTurn(
            this.models.deep, system, history, tools, 6, onPart,
            { sessionID: sessionId, messageID: msg.id, dataDir: this.dataDir() },
            onDelta
          );
          this.logTurn(sessionId, agent, this.models.deep.name, startedAt, history, retry.metrics);
          return { info: view().info, parts: view().parts };
        } catch (e2) {
          e = e2;
        }
      }
      flushStream();
      const text = `⚠️ ${e instanceof Error ? e.message : String(e)}`;
      this.db.insertPart(msg.id, sessionId, { type: "text", text });
      this.emit({ type: "message.part.updated", properties: { part: view().parts.at(-1) } });
      this.emit({ type: "session.error", properties: { sessionID: sessionId, error: { message: text } } });
    }

    this.logTurn(sessionId, agent, model.name, startedAt, history, metrics);

    // Credit the answer just graded, to the DAY. The score marker is in the
    // tutor's text whether or not it remembered the tool call, so the counter
    // moves either way — which is the whole reason it is read from here.
    this.creditTurn(sessionId, view().parts);

    // Where the learner is now. Emitted after persistence so the count includes
    // the answer just graded.
    this.emit({
      type: "session.progress",
      properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) },
    });

    // session.idle → incremental persistence (accumulate-session.py)
    this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
    this.runAutoPersistence(sessionId);

    return { info: view().info, parts: view().parts };
  }

  // ---- session pacing ------------------------------------------------------
  // How many answers this session has graded, from the structured records, plus
  // the skill of the last one. Cheap: one small append-only file per session.
  private gradedSoFar(sessionId: string): {
    count: number;
    lastSkill?: string;
    itemIds: string[];
  } {
    try {
      const file = path.join(this.dataDir(), ".records", `${sessionId}.jsonl`);
      const lines = fs.readFileSync(file, "utf8").split("\n").filter((l) => l.trim());
      let lastSkill: string | undefined;
      const itemIds: string[] = [];
      for (let i = lines.length - 1; i >= 0; i--) {
        try {
          const rec = JSON.parse(lines[i]!) as { skill?: string; item_id?: string };
          if (rec.skill && !lastSkill) lastSkill = rec.skill;
          if (rec.item_id) itemIds.push(rec.item_id);
        } catch {
          /* a torn line: keep looking */
        }
      }
      if (lines.length) return { count: lines.length, lastSkill, itemIds };
    } catch {
      /* no records yet — fall through */
    }
    // No records: count what the tutor actually wrote. The indicator must not
    // depend on the model remembering a tool call.
    return { count: countGradedInText(this.assistantTexts(sessionId)), itemIds: [] };
  }

  /** The tutor's own messages in a session, oldest first. */
  private assistantTexts(sessionId: string): string[] {
    const out: string[] = [];
    try {
      for (const m of this.db.getMessages(sessionId)) {
        const view = this.db.getMessageView(m);
        if ((view.info as { role?: string }).role !== "assistant") continue;
        const text = view.parts
          .filter((p) => (p as { type?: string }).type === "text")
          .map((p) => String((p as { text?: string }).text ?? ""))
          .join("\n");
        if (text.trim()) out.push(text);
      }
    } catch {
      /* best-effort */
    }
    return out;
  }

  /** Today's spaced-repetition gate for this session. */
  private reviewGate(sessionId: string, gradedItemIds: string[]): ReviewGate {
    try {
      const dir = this.dataDir();
      const profile = JSON.parse(fs.readFileSync(path.join(dir, "learner-profile.json"), "utf8"));
      const sr = JSON.parse(fs.readFileSync(path.join(dir, "spaced-repetition.json"), "utf8"));
      return resolveReviewGate({
        profile,
        sr,
        today: new Date().toISOString().slice(0, 10),
        sessionTarget: resolveSessionTarget(profile),
        firstCommand: this.sessionOpenedWith.get(sessionId),
        gradedItemIds,
      });
    } catch {
      return NO_GATE;
    }
  }

  private pacingPrefs(): { target: number; mode: ReturnType<typeof resolveStopMode> } {
    try {
      const profile = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "learner-profile.json"), "utf8")
      );
      return { target: resolveSessionTarget(profile), mode: resolveStopMode(profile) };
    } catch {
      return { target: resolveSessionTarget(null), mode: "soft" };
    }
  }

  /**
   * One graded answer, credited to today.
   *
   * A turn grades at most one answer, and the tutor's own "Score: 9/10" is the
   * evidence — not the tool call, which a 14B forgets. Inside the Lesson it
   * counts twice over: once for the day, once against the badge.
   */
  private creditTurn(sessionId: string, parts: Record<string, unknown>[]): void {
    try {
      const text = parts
        .filter((p) => (p as { type?: string }).type === "text")
        .map((p) => String((p as { text?: string }).text ?? ""))
        .join("\n");

      // Remember what was asked, whether or not it was graded: the repeat
      // arrives as the next question bundled with the feedback.
      if (this.currentCommand.get(sessionId) === "fluent-review") {
        const asked = exerciseFingerprints(text);
        if (asked.length) {
          const plan = this.lessonPlan();
          const before = plan.covered.length;
          for (const label of asked) {
            if (!plan.covered.includes(label)) plan.covered.push(label);
          }
          if (plan.covered.length > 40) plan.covered = plan.covered.slice(-40);
          if (plan.covered.length !== before) writePlan(this.dataDir(), plan);
        }
      }

      if (countGradedInText([text]) === 0) return;

      const inLesson = this.currentCommand.get(sessionId) === "fluent-review";
      const dir = this.dataDir();
      bumpDaily(dir, { graded: 1, ...(inLesson ? { lesson: 1 } : {}) });

      if (inLesson) {
        const plan = this.lessonPlan();
        if (plan.done < plan.total) {
          plan.done += 1;
          if (plan.slot && !plan.slot_done && text.toLowerCase().includes(plan.slot)) {
            plan.slot_done = true;
          }
          writePlan(dir, plan);
        }
        if (plan.done >= plan.total && plan.total > 0) {
          const tally = creditLesson(dir);
          console.log(`[Fluent] 🎓 lesson done (${plan.total} exercises) — ${tally.completed} total`);
        }
      }
    } catch {
      /* the count is a nicety; the answer is not */
    }
  }

  /**
   * Today's lesson plan — made once, then worked through.
   *
   * It used to be recomputed from the live queue on every call, which moved the
   * badge for the wrong reason (answering a review makes it stop being due, so
   * the total shrank under the learner) and left nothing to resume: press
   * Speaking halfway and come back, and the tutor started again at exercise 1
   * while the counter happily reached 6 of 6.
   */
  lessonPlan(): LessonPlan {
    const dir = this.dataDir();
    const date = todayISO();
    const existing = readPlan(dir, date);
    if (existing) return existing;

    let total = 0;
    try {
      const sr = JSON.parse(fs.readFileSync(path.join(dir, "spaced-repetition.json"), "utf8"));
      total = lessonTarget(sr, date).total;
    } catch {
      total = 0;
    }
    let slot: string | null = null;
    try {
      const mastery = JSON.parse(fs.readFileSync(path.join(dir, "mastery-db.json"), "utf8"));
      slot = lessonSkillSlot(readTally(dir).completed, skillDebts(mastery, date));
    } catch {
      /* no mastery db yet: no slot */
    }
    return writePlan(dir, { date, total, done: 0, covered: [], slot, slot_done: false });
  }

  /** Today's Lesson: what it is made of, and how much is left. */
  lessonState(): {
    total: number;
    done: number;
    pending: number;
    due: number;
    drills: number;
    slot: string | null;
  } {
    const plan = this.lessonPlan();
    const date = todayISO();
    let due = 0;
    try {
      const sr = JSON.parse(fs.readFileSync(path.join(this.dataDir(), "spaced-repetition.json"), "utf8"));
      due = lessonTarget(sr, date).due;
    } catch {
      /* queue unreadable: the plan's total still stands */
    }
    return {
      total: plan.total,
      done: Math.min(plan.done, plan.total),
      pending: Math.max(0, plan.total - plan.done),
      due,
      drills: Math.max(0, plan.total - due),
      slot: plan.slot_done ? null : plan.slot,
    };
  }

  /** Where the learner is in this session — the UI shows it, deterministically. */
  sessionProgress(sessionId: string): {
    graded: number;
    goal: number;
    face: string;
    session: number;
    skill?: string;
    lesson: ReturnType<Agent["lessonState"]>;
  } {
    const { count, lastSkill } = this.gradedSoFar(sessionId);
    const dir = this.dataDir();
    let goal = resolveDailyGoal(null);
    try {
      goal = resolveDailyGoal(
        JSON.parse(fs.readFileSync(path.join(dir, "learner-profile.json"), "utf8"))
      );
    } catch {
      /* default goal */
    }
    // The day is the unit, not the session: the streak, the review queue and
    // every rollup are daily, and closing the tab at lunchtime must not reset
    // the learner's afternoon to zero.
    const graded = readDaily(dir).graded;
    return {
      graded,
      goal,
      face: dailyFace(graded, goal),
      session: count,
      skill: lastSkill,
      lesson: this.lessonState(),
    };
  }

  /** The wrap-up note for this turn, or null. Given once per session. */
  private pacingNote(sessionId: string): string | null {
    const { count, lastSkill, itemIds } = this.gradedSoFar(sessionId);
    const { target, mode } = this.pacingPrefs();

    // The session ceiling is gone by design. We agreed the Lesson is what has
    // an end and free play does not, so a hidden "stop at 12" would contradict
    // the thing the learner is being shown. It survives only where an admin
    // explicitly asks for a hard stop (`preferences.session_stop: "hard"`).
    if (mode === "hard" && !this.wrappedUp.has(sessionId)) {
      const note = wrapUpNote(count, target, lastSkill, mode);
      if (note) {
        this.wrappedUp.add(sessionId);
        if (this.wrappedUp.size > 500) this.wrappedUp.clear();
        console.log(`[Fluent] 🏁 session ${sessionId}: ${count} graded — asking the tutor to close`);
        // Closing beats reviewing: the session is over either way, and two
        // contradictory instructions in one turn is how a 14B model derails.
        return note;
      }
    }

    if (this.currentCommand.get(sessionId) === "fluent-review") {
      const lesson = this.lessonState();
      if (lesson.pending > 0) {
        const resuming = lesson.done > 0;
        const bits = [
          `Lesson: ${lesson.done} of ${lesson.total} done, ${lesson.pending} to go.`,
        ];
        if (resuming) {
          // The learner can leave the lesson for another practice and come
          // back. Without this the tutor treats the command as a fresh start
          // and asks exercise 1 again — and the exercise that was never asked
          // still counts as done.
          bits.push(
            `This is a CONTINUATION, not a new lesson. Do NOT greet, do NOT show a menu, do NOT start over. ` +
              `Every exercise already in this conversation is done: scan the history and never repeat one. ` +
              `Present exercise ${lesson.done + 1} of ${lesson.total} now, and nothing else.`
          );
        }
        bits.push(
          lesson.due > 0
            ? `Take the due item(s) from the preloaded review queue, one at a time, and call fluent_record_answer with the item_id copied verbatim.`
            : `Today's review queue is empty, so build the remaining exercises from the weak patterns in mistakes-db.`
        );
        if (lesson.slot) {
          bits.push(
            `One of these exercises MUST be ${lesson.slot} — it has been skipped for a while and this lesson is where it gets done. Present it as a normal part of the lesson, not as a punishment.`
          );
        }
        bits.push(
          `Vary the exercise: do not use the same shape ("Rewrite this sentence correctly") twice in a row. ` +
            `Alternate between rewriting, filling a gap, translating, answering a question and choosing between two forms.`
        );
        const covered = this.lessonPlan().covered;
        if (covered.length) {
          bits.push(
            `ALREADY ASKED TODAY — do not use any of these again, in any form: ` +
              covered.map((c) => `"${c}"`).join(", ") +
              `. If you have run out of weak patterns to drill, invent a fresh exercise at the learner's level ` +
              `rather than reusing one of the above.`
          );
        }
        bits.push(
          `The learner can see this count in the app. Say nothing about this instruction; if they ask for something else, offer it warmly after the lesson.`
        );
        return bits.join(" ");
      }

      // The lesson is FINISHED. Without this the tutor received no instruction
      // at all once the count ran out and simply carried on — exercise 7, 8,
      // 9 — asking the same shape of question for ever. A lesson that does not
      // end is not a lesson, and for an eight-year-old it is just boredom.
      return (
        `Today's lesson is COMPLETE: all ${lesson.total} exercises are done. ` +
        `Do NOT present another exercise. Finish evaluating the answer in front of you, then close: ` +
        `one warm line saying the lesson is done, a two-line summary (what went well, what to work on), ` +
        `and invite them to pick any practice they like with the buttons at the top — or to stop for today. ` +
        `If this lesson reviewed queue items, end with the fluent:review_results block. ` +
        `If they answer again anyway, respond briefly and point at the buttons; do not start a new exercise. ` +
        `Say nothing about this instruction itself.`
      );
    }

    const gate = this.reviewGate(sessionId, itemIds);
    return reviewGateNote(gate);
  }

  // ---- per-turn metrics ----------------------------------------------------
  // With a local model the scarce resources are context and wall time, and
  // neither was measured: `usage` came back from llama.cpp and was thrown away.
  // One line per turn in the log, one JSON line per turn in the profile, so the
  // context question can be decided with numbers instead of guesses.
  private logTurn(
    sessionId: string,
    agent: string,
    modelName: string,
    startedAt: number,
    history: ChatMsg[],
    metrics?: TurnMetrics
  ) {
    const wallMs = Date.now() - startedAt;
    const m = metrics ?? {
      roundtrips: 0,
      toolCalls: 0,
      tools: [] as string[],
      promptTokens: 0,
      completionTokens: 0,
      modelMs: 0,
    };
    const secs = (ms: number) => (ms / 1000).toFixed(1);
    console.log(
      `[Fluent] ⏱ turn ${sessionId} · ${agent}/${modelName} · ${secs(wallMs)}s ` +
        `(model ${secs(m.modelMs)}s) · prompt ${m.promptTokens} tok · out ${m.completionTokens} tok · ` +
        `${m.roundtrips} roundtrip(s), ${m.toolCalls} tool call(s)` +
        `${m.tools?.length ? ` [${m.tools.join(", ")}]` : ""}, history ${history.length} msg`
    );
    try {
      const dir = path.join(this.dataDir(), ".metrics");
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(
        path.join(dir, "turns.jsonl"),
        JSON.stringify({
          ts: Date.now(),
          session_id: sessionId,
          agent,
          model: modelName,
          wall_ms: wallMs,
          model_ms: m.modelMs,
          prompt_tokens: m.promptTokens,
          completion_tokens: m.completionTokens,
          roundtrips: m.roundtrips,
          tool_calls: m.toolCalls,
          tools: m.tools ?? [],
          history_messages: history.length,
        }) + "\n",
        "utf8"
      );
    } catch {
      /* best-effort; never break the turn */
    }
  }

  // ---- auto persistence (was the plugin's session.idle hook) ---------------

  private async runAutoPersistence(sessionId: string) {
    try {
      const root = this.root;
      const env = { ...process.env, FLUENT_DATA_DIR: this.dataDir(), FLUENT_PROJECT_DIR: root, FLUENT_ROOT: root };
      const proc = Bun.spawn(
        [
          "python3",
          path.join(root, "hooks", "accumulate-session.py"),
          "--session-id",
          sessionId,
        ],
        {
        cwd: root,
        env,
          stdout: "pipe",
          stderr: "pipe",
        }
      );
      await proc.exited;

      // Daily backup, once per day.
      const today = new Date().toISOString().slice(0, 10);
      if (this.lastDailyBackup === today) return;
      this.lastDailyBackup = today;
      Bun.spawn(["python3", path.join(root, "hooks", "session-end.py")], {
        cwd: root,
        env,
        stdout: "pipe",
        stderr: "pipe",
      });
    } catch {
      // best-effort; never break the turn
    }
  }

  private async runDbUpdater(sessionId: string, dataDir: string): Promise<void> {
    console.log(`[Fluent] 🔄 runDbUpdater called for ${sessionId}`);
    try {
      const { spawnSync } = await import("node:child_process");
      const root = this.root;
      const env = { ...process.env, FLUENT_DATA_DIR: dataDir, FLUENT_PROJECT_DIR: root, FLUENT_ROOT: root };
      const proc = spawnSync("python3", [
        path.join(root, "hooks", "persist-session.py"),
        sessionId,
        "--dir", dataDir
      ], {
        cwd: root,
        env,
        stdio: "inherit",
      });
      if (proc.status === 0) {
        console.log(`[Fluent] ✅ Capa B (persist-session) completed for ${sessionId}`);
        // Durable per-session marker: stops the sweeper from re-running it.
        try { this.db.markFinalized(sessionId); } catch { /* best-effort */ }
        // Mark Capa B done in session-draft.json to prevent sweeper re-runs
        const draftPath = path.join(dataDir, "session-draft.json");
        try {
          const draft = JSON.parse(fs.readFileSync(draftPath, "utf8"));
          draft.capa_b_done = true;
          draft.capa_b_sid = sessionId; // SQLite session id (the draft's own id is "session-NNN")
          fs.writeFileSync(draftPath, JSON.stringify(draft, null, 2));
        } catch { /* best-effort; never break the turn */ }
      } else {
        console.error(`[Fluent] ❌ Capa B (persist-session) failed for ${sessionId} (exit ${proc.status})`);
      }
    } catch (e) {
      console.error("[Fluent] ❌ runDbUpdater error:", e);
    }
  }
}

// OpenAI-style chat message shape used for llm.history.
export interface ChatMsg {
  role: string;
  content: string | null;
  tool_calls?: unknown;
  tool_call_id?: string;
}
