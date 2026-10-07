// Fluent server — the agent orchestrator.
// Runs a "turn" (a /math-* command or a learner chat message) over the LLM,
// persists every produced part into the SQLite bridge, and emits SSE events so
// the web UI renders incrementally (same contract opencode exposed).

import fs from "node:fs";
import path from "node:path";
import type { FluentDB, SessionRow, MessageRow } from "./db";
import { runTurn, type ToolDefinition, type TurnPart, type ModelConfig, type ToolStep, type TurnMetrics } from "./llm";
import { buildTools, normalizeCategory, type DeepEvaluator } from "./tools";
import { loadCommand } from "./commands";
import { bankExerciseCard, bankFeedback, difficultyLabel, type BankItem, type BankGrade } from "./bank";
import { stepsV2Init, stepsV2Handle, stepsV2Note, stepsV2Resume, type StepsV2State } from "./steps";
import {
  resolveSessionTarget,
  resolveStopMode,
  isPaced,
  wrapUpNote,
  countGradedInText,
  KNOWN_SCORE,
  scoreOfReply,
  parseTopics,
  exerciseOnlyOf,
  isExerciseGuard,
  isFeedbackGuard,
  mergeFeedbackOnly,
  trailingExercise,
  topicsNote,
  lessonTarget,
  lessonSkillSlot,
  skillBadge,
  skillDebts,
  exerciseFingerprints,
  pruneHistory,
  historyBudget,
  estimateTokens,
  dailyFace,
  resolveDailyGoal,
  lessonNote,
  skillBlock,
  drillMaterial,
  parseFeedback,
  alignMarkersToScore,
  stripTemplateBraces,
  feedbackFromRecord,
  spliceFeedback,
  withAnswerInFront,
  alignLessonHeader,
  turnGuard,
  pictureGuard,
  writingBlankGuard,
  reasoningTaskGuard,
  wordProblemTaskGuard,
  hasExerciseHeader,
  alignExerciseNumber,
  bounceReason,
  stripCompetencyLeak,
  tagCompetency,
  type AssignedCompetence,
  nextDueItem,
  practiceNote,
  type AssignedItem,
  type LessonView,
} from "./pacing";
import {
  foreignScriptGuard,
  languageDirectionGuard,
  stripForeignScript,
  foreignScript,
  vocabularyDueNote,
  writingLengthNote,
} from "./domain-language";
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
  /** Server-only signal, never written by the model — whether this session's
   *  practice actually has its skill (grading contract, exercise rules)
   *  loaded right now, and how full the context is. Exists because the two
   *  ways this silently breaks (activeSkill wiped by a restart; history
   *  trimmed to fit ctx) leave no trace in the chat itself — measured live,
   *  2026-09-23: 20+ turns of "10/10, 0 corrections" with a wrong has/have
   *  answer, and nothing in the transcript said why. The UI turns this into
   *  a small dot; it never reaches the model or the learner's history. */
  debug?: {
    skillLoaded: boolean;
    skillName?: string;
    promptTokens?: number;
    ctxLimit: number;
    ctxRatio?: number;
  };
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

const OPEN_PRACTICES = new Set(["math-speaking", "math-writing", "math-reading"]);

// Which math practice (C7 skill key) a command runs. A derived record — the
// fallback for a tutor that graded in prose and skipped math_record_answer —
// knows the practice from the active command, which beats guessing it from a
// heading that may not name one at all.
const COMMAND_SKILL: Record<string, string> = {
  "math-writing": "reasoning",
  "math-speaking": "reasoning",
  "math-reading": "problems",
  "math-vocab": "facts",
  "math-learn": "computation",
};

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
  /** The practice mode a session is in right now (last command pressed). */
  private currentCommand = new Map<string, string>();
  /** The SKILL.md that governs the practice the learner is in right now, pinned
   *  to the SYSTEM prompt for the rest of the session. System, not history: the
   *  history is pruned when the context fills, and the grading contract is the
   *  last thing that may quietly disappear. */
  private activeSkill = new Map<string, { name: string; body: string }>();
  /** The learner-state block (read-db.py output) for this session, pinned to
   *  the system prompt so the history's pruning can never take it away. */
  private activeState = new Map<string, string>();
  /** Fingerprints of the exercise the tutor asked last turn, per session. */
  private lastAsked = new Map<string, string[]>();
  /** The learner's last message, so a record derived from the tutor's text can
   *  say what was actually answered. */
  private lastAnswer = new Map<string, string>();
  /** True while the turn being run was opened by the learner typing an answer;
   *  false for a button. Only an answer can be the one that finishes a lesson. */
  private answerInFront = new Map<string, boolean>();
  /** The bank item behind the exercise on screen, when Go/Vocabulary is
   *  running off curriculum/bank/*.json instead of the model. Cleared once
   *  graded. See PLA-EXERCICIS-TANCATS.md. */
  private assignedBankItem = new Map<
    string,
    {
      competence: string; itemId: string; practice?: "go" | "review";
      queueId?: string | null; item?: BankItem; vocab?: boolean; name?: string; depth?: string;
      /** WP2.5: a steps item served v2-style (one step per message). The
       *  per-session analogue of `gradingItem`: which step is pending and how
       *  many attempts it has had. Cleared with the item when the trace is
       *  finalized (or abandoned by a practice switch). */
      stepsV2?: StepsV2State;
    }
  >();
  /** The review item the server handed the tutor for the exercise now on
   *  screen, and the one before it — the answer arriving this turn belongs to
   *  the previous assignment, not the one being made now. */
  private assignedItem = new Map<string, AssignedItem>();
  private gradingItem = new Map<string, AssignedItem>();
  /** The same, for the curriculum's competence in free practice (Mix, Vocabulary):
   *  the one the exercise now on screen was built for, and the one being graded.
   *  `followed` is set once the tutor's exercise was seen to be about it. */
  private assignedCompetence = new Map<string, AssignedCompetence & { followed?: boolean; shown?: boolean }>();
  private gradingCompetence = new Map<string, AssignedCompetence & { followed?: boolean; shown?: boolean }>();
  /** Items dispensed today, so the queue is not handed out twice — the MODEL
   *  review path's list (pacingNote pre-assigns from it). */
  private usedItems = new Map<string, string[]>();
  /** The BANK review path's own served list (queueIds it handed out). Kept
   *  apart from `usedItems` on purpose: pacingNote pre-assigns a due item on
   *  EVERY turn for the model path, and on the bank path those pre-assignments
   *  are never served — mixing the two lists made review-pick skip the first
   *  due item of every lesson (fixed in e0057b4 by filtering the current
   *  pick), and a v2 steps exchange, which spans many turns on ONE item while
   *  pacingNote advances its pick each turn, broke that single-pick filter
   *  both ways (found by the WP2.5 e2e: items skipped, then re-served). */
  private bankUsedItems = new Map<string, string[]>();
  /** Weak patterns already drilled this session, and the one in hand. */
  /** What each practice has asked today, keyed "<session>|<command>". */
  private askedByPractice = new Map<string, string[]>();
  /** How many turns in a row the pacing note has said exactly the same thing.
   *  An unchanging note means the lesson is not advancing — worth a log line,
   *  because on 2026-09-16 it stayed unchanged for twenty-five turns and
   *  nobody found out until the children gave up. */
  private noteStall = new Map<string, { note: string; turns: number }>();
  /** The running number for "## Exercise {N}: ..." / "## Question {N}: ..."
   *  headings, per session+practice — see alignExerciseNumber. */
  private exerciseSeq = new Map<string, number>();
  /** Consecutive answered turns that produced no detectable grade — see
   *  bounceReason. Reset to 0 the moment a turn grades again. */
  private ungradedStreak = new Map<string, number>();
  /** Sessions already bounced once — never twice in a row for the same
   *  session, so a fresh session that is itself unlucky does not loop. */
  private bounced = new Set<string>();

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
    this.tools = buildTools({
      root: opts.root,
      dataDir: opts.dataDir,
      deep: opts.deep,
      gradingItem: (sessionId) => this.gradingItem.get(sessionId) ?? null,
      gradingCompetence: (sessionId) => this.recordCompetence(sessionId),
    });
  }

  private dataDir() {
    return this.dataDirFn();
  }

  /** The deep model's context window, from config. */
  private contextTokens(): number {
    const n = Number(process.env.FLOWED_DEEP_CTX);
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

  /** Builds TurnOutcome.debug — see its doc comment for why this exists.
   *  Never touches the model or the learner's history; purely server-side
   *  bookkeeping the UI can render as a status dot. */
  private debugStatus(sessionId: string, promptTokens?: number): TurnOutcome["debug"] {
    const skill = this.activeSkill.get(sessionId);
    const ctxLimit = this.contextTokens();
    return {
      skillLoaded: Boolean(skill),
      skillName: skill?.name,
      promptTokens,
      ctxLimit,
      ctxRatio: promptTokens ? Math.round((promptTokens / ctxLimit) * 100) / 100 : undefined,
    };
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

  /** Speaking, Writing and Reading: the server records the answer from the
   *  feedback text (deriveRecord), so the model is not offered
   *  math_record_answer there. Tutor-bench, 2026-09-29 (docs/MODELBENCH.md):
   *  the call cost a second full request of ~17k tokens per answer (27B: 2
   *  round-trips per turn, ~60 s), and 5 of 17 times the score it stored was
   *  not the one it showed. The 14B was already stored this way 21 times in 30. */
  private recordsFromText(sessionId?: string): boolean {
    return OPEN_PRACTICES.has(sessionId ? this.currentCommand.get(sessionId) ?? "" : "");
  }

  private toolsFor(sessionId: string): ToolDefinition[] {
    return this.recordsFromText(sessionId)
      ? this.tools.definitions.filter((t) => t.name !== "math_record_answer")
      : this.tools.definitions;
  }

  private buildSystemPrompt(agent: string, sessionId?: string): string {
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
    // WP5.2: the domain's own rules load LAST, so they win over the shared
    // ones (rules-<domain>.md; missing file = nothing extra).
    const domRules = this.readRuleFile(path.join("prompts", "agents", `rules-${this.domainForSession()}.md`)).trim();
    if (domRules) blocks.push(`Domain rules (apply on top of everything above):\n\n${domRules}`);
    // The practice the learner is in. Last block, so it wins any generic rule
    // above it, and present on EVERY turn — not only on the turn that happened
    // to load it.
    const state = sessionId ? this.activeState.get(sessionId) : undefined;
    if (state) {
      blocks.push(
        `Who you are teaching right now, and where they are. This is the live state ` +
          `of their profile and databases — treat it as fact:\n\n${state}`
      );
    }
    const practice = skillBlock(sessionId ? this.activeSkill.get(sessionId) : undefined);
    if (practice) blocks.push(practice);
    if (this.recordsFromText(sessionId)) {
      blocks.push(
        `Recording, in this practice: the server stores each answer from your feedback text. ` +
          `math_record_answer is NOT available here — do not call it and do not mention it. ` +
          `Your feedback must show "**Score: N/10**" and each correction as ❌ "wrong" → **"right"**, ` +
          `and then continue with the next question or task in the same message.`
      );
    }
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
      model: { providerID: "math-deep", modelID: "deep" },
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
      model: { providerID: model.name === "deep" ? "math-deep" : "llama-face", modelID: model.name },
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
    // Which practice the learner is in right now — the Lesson credits only
    // answers given inside it.
    const prevCommand = this.currentCommand.get(sessionId);
    // WP5.2: the practice LOGIC keys on the canonical (math-*) name, so the
    // engine is domain-neutral (a fluent-review behaves as the review lesson);
    // loading and labels keep the RAW domain name below.
    const cmdKey = commandName.replace(/^fluent-/, "math-");
    this.currentCommand.set(sessionId, cmdKey);
    if (this.currentCommand.size > 500) this.currentCommand.clear();
    this.answerInFront.set(sessionId, false);
    // The level test is run by the server (docs/ESQUEMA-APRENENTATGE.md): no model in the loop.
    if (cmdKey === "math-checkpoint") return this.checkpointTurn(sessionId, "start", "");
    // A button starts a new exercise in a new practice, so the previous practice's
    // exercise is no longer the one being answered. Left standing, a Writing
    // answer was graded as the answer to the Vocabulary word shown before it
    // ("llibre" ← "I have two childs…"): the note said so, the tutor obeyed, and
    // two false records went to the database. The reply to the button sets it
    // again when it presents an exercise the fingerprints recognise.
    this.lastAsked.delete(sessionId);
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
    // the greeting template). Skipped for math-end (own finalization flow).
    let body = resolved.body;
    if (cmdKey !== "math-end" && continuing) {
      // Measured live, 2026-09-22, test-en: pressing Reading right after Speaking
      // did not switch the content — the tutor kept asking Speaking-style
      // "Question N" cards under the Reading button, twice in one session. The
      // generic "continue the ongoing practice" wording did not say WHICH
      // practice, so with Speaking still fresh in the history the model just
      // kept going. When the button actually changed the practice, say so by
      // name and say to drop the previous one — the same instruction a switch
      // between any two skills needs, not just this pair.
      body +=
        prevCommand && prevCommand !== commandName
          ? `\n\n(Switching practice: the history above contains turns from ${prevCommand}, but the learner just pressed the button for ${commandName}. Do NOT greet, do NOT show the practice menu, and do NOT continue ${prevCommand}'s exercises — stop that practice now and follow ONLY the ${commandName} instructions above for the next exercise.)`
          : `\n\n(Continuing session: the history above already contains tutor turns. Do NOT greet, do NOT show the practice menu — continue the ongoing practice directly: evaluate any pending answer, otherwise present the next exercise.)`;
    }
    if (resolved.skill) {
      this.activeSkill.set(sessionId, resolved.skill);
      if (this.activeSkill.size > 200) this.activeSkill.clear();
    }
    if (resolved.state) {
      this.activeState.set(sessionId, resolved.state);
      if (this.activeState.size > 200) this.activeState.clear();
    }
    this.persistUserTurn(sessionId, body, agent, true);
    const system = this.buildSystemPrompt(agent, sessionId);
    const history = this.historyToMessages(sessionId);
    const outcome = await this.executeTurn(sessionId, agent, system, history, this.toolsFor(sessionId));

    // Auto-run math-db-updater for math-end command to finalize Capa B
    if (cmdKey === "math-end") {
      await this.runDbUpdater(sessionId, dataDir);
    }

    return outcome;
  }

  async runMessage(sessionId: string, text: string, agentArg: string): Promise<TurnOutcome> {
    const agent = agentArg || "learner";
    // A test in progress answers itself: the server asks, grades and cuts the course.
    const cmd = this.currentCommand.get(sessionId);
    if ((cmd === "math-checkpoint" || cmd === undefined) && this.checkpointRunning()) {
      return this.checkpointTurn(sessionId, "answer", text);
    }
    // currentCommand lives only in memory: every server restart wipes it, and a
    // session mid-practice is left with NO mode at all — silently. Everything
    // gated on it (curriculum competence, exercise numbering, the Lesson's own
    // pacing) then switches off with nothing in the log to say why. Measured
    // 2026-09-22: a practice ran a dozen turns like this, unnoticed, after a
    // routine restart mid-session. A message answering something already on
    // screen is always INSIDE a mode, never the start of one, so recover it
    // instead of leaving it unset — Go is the general-purpose practice, the
    // reasonable default when the specific one that was active cannot be known.
    if (cmd === undefined && this.sessionHasAssistantText(sessionId)) {
      this.currentCommand.set(sessionId, "math-learn");
      console.log(`[Fluent] ↺ session ${sessionId}: no mode in memory (restart?) — defaulting to math-learn`);
      // currentCommand was not the only thing the restart wiped: activeSkill
      // (the grading contract, exercise-type rules, the closing-line marker
      // rule — everything in skillBlock()) lives in the same kind of
      // in-memory Map and is gone too, silently — buildSystemPrompt just
      // omits the block when the Map has nothing for this session. Measured
      // 2026-09-23: 20+ turns after a mid-practice restart, every answer
      // graded "10/10, 0 correction(s)" including a wrong "have"/"has"
      // agreement — the model was not grading anymore, it had no contract to
      // grade against. Reload it the same way runCommand does on a fresh
      // command, skipping directives (this session already has its state in
      // history; re-running read-db.py here would just re-inject it).
      if (!this.activeSkill.has(sessionId)) {
        // Awaited, not fire-and-forget: buildSystemPrompt() runs later in
        // THIS SAME turn and reads activeSkill synchronously — a detached
        // .then() would only land in time for the turn after this one.
        try {
          const resolved = await loadCommand("math-learn", {
            root: this.root,
            dataDir: this.dataDir(),
            env: { ...process.env as Record<string, string> },
            skipDirectives: true,
          });
          if (resolved?.skill) {
            this.activeSkill.set(sessionId, resolved.skill);
            if (this.activeSkill.size > 200) this.activeSkill.clear();
          }
        } catch {
          /* best-effort; the turn proceeds without the skill rather than failing */
        }
      }
    }
    this.answerInFront.set(sessionId, true);
    if (this.answerInFront.size > 500) this.answerInFront.clear();
    this.lastAnswer.set(sessionId, text);
    if (this.lastAnswer.size > 500) this.lastAnswer.clear();
    this.persistUserTurn(sessionId, text, agent, false);
    const system = this.buildSystemPrompt(agent, sessionId);
    return this.executeTurn(sessionId, agent, system, this.historyToMessages(sessionId), this.toolsFor(sessionId));
  }

  // ---- the level test ------------------------------------------------------
  // Picked, asked and graded by hooks/curriculum.py (`checkpoint start|answer`); this
  // only carries its text into the conversation as a tutor message. Nothing here
  // depends on the model, so a certificate never depends on a model's mood.

  /** A test started TODAY and not finished (after a restart the map of commands is empty, and the
   *  next message is still the answer to the question on screen). */
  private checkpointRunning(): boolean {
    try {
      const run = JSON.parse(fs.readFileSync(path.join(this.dataDir(), "checkpoint-run.json"), "utf8")) as { day?: string };
      return run.day === new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
    } catch {
      return false;
    }
  }

  private runCheckpointCli(action: "start" | "answer", text: string): { ok: boolean; text: string; done?: boolean } {
    try {
      const args = [
        "python3", path.join(this.root, "hooks", "curriculum.py"), "checkpoint", action, "--auto",
        "--data", this.dataDir(), "--today", new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
      ];
      if (action === "answer") args.push("--text", text);
      const r = Bun.spawnSync(args, {
        cwd: this.root,
        env: { ...process.env, FLOWED_DATA_DIR: this.dataDir(), FLOWED_ROOT: this.root },
        stdout: "pipe",
        stderr: "pipe",
      });
      const j = JSON.parse(r.stdout.toString() || "{}") as { ok?: boolean; text?: string; done?: boolean };
      if (r.exitCode === 0 && typeof j.text === "string") return { ok: Boolean(j.ok), text: j.text, done: j.done };
    } catch {
      /* fall through */
    }
    return { ok: false, text: "The level test is not available right now. Please try again later." };
  }

  private async checkpointTurn(sessionId: string, action: "start" | "answer", text: string): Promise<TurnOutcome> {
    const agent = "learner";
    this.db.touchSession(sessionId);
    this.persistUserTurn(sessionId, action === "start" ? "Execute /math-checkpoint now." : text, agent, action === "start");
    const out = this.runCheckpointCli(action, text);
    const { model } = await resolveModel(agent, this.models);
    const msg = this.createAssistantMessage(sessionId, agent, model);
    const view = () => this.db.getMessageView(msg);
    this.db.insertPart(msg.id, sessionId, { type: "text", text: out.text });
    this.emit({ type: "message.part.updated", properties: { part: view().parts.at(-1) } });
    // The test is over (or could not start): the next message is an ordinary one.
    if (out.done || !out.ok) this.currentCommand.delete(sessionId);
    this.emit({ type: "session.progress", properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) } });
    this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
    return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId) };
  }

  /** config/fluent.json → exercises.bank. Off by default; a competence still
   *  needs its own curriculum/bank/<curriculum>/<id>.json to actually use it. */
  private bankEnabled(): boolean {
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(this.root, "config", "fluent.json"), "utf8"));
      return Boolean(cfg?.exercises?.bank);
    } catch {
      return false;
    }
  }

  private runBankCli(args: string[]): Record<string, unknown> | null {
    try {
      const r = Bun.spawnSync(
        ["python3", path.join(this.root, "hooks", "curriculum.py"), "bank", ...args, "--auto", "--data", this.dataDir()],
        { cwd: this.root, timeout: 5000 }
      );
      if (r.exitCode !== 0) return null;
      return JSON.parse(r.stdout.toString() || "{}");
    } catch {
      return null;
    }
  }

  /** Writes a record in the exact shape math_record_answer (tools.ts) writes,
   *  so curriculum.py's pacing and the reports read it the same either way —
   *  the bank replaces the model's grading, not the record format it produces. */
  private appendBankRecord(
    sessionId: string, competenceId: string, vocab: boolean, graded: Record<string, unknown>, queueId?: string | null
  ): void {
    const score = Math.round(Number(graded.score ?? 0));
    const correctVersion = String(graded.correct_version ?? "");
    const item = (graded.item ?? {}) as Record<string, unknown>;
    const itemType = String(item.type ?? "");
    // Same dispatch as hooks/bank.py and bank.ts: math items (compute/compare,
    // or a choose built on a `problem`) are graded by mathgrade and filed under
    // the math taxonomy; language items keep the vocab/spelling/grammar split.
    const isMath =
      itemType === "compute" || itemType === "compare" || itemType === "steps" ||
      (itemType === "choose" && item.problem && !item.sentence);
    const verdict = String(graded.verdict ?? "");
    // A steps item names its own category: the FIRST failed step's error_class
    // (hooks/bank.py `_grade_steps`); near is always "calculation" (a digit
    // slip), same rule as the other math verdicts.
    const category = isMath
      ? verdict === "near" ? "calculation" : String(graded.error_class || item.error_class || "calculation")
      : vocab ? "vocabulary" : verdict === "typo" ? "spelling" : "grammar";
    // WP2.3: a steps record carries the per-step trace — one entry per
    // expected step, `got` the learner's line or null, `propagated` on every
    // step after the first failure (additive: nothing else reads it yet).
    const stepTrace = Array.isArray(graded["steps"])
      ? (graded["steps"] as Record<string, unknown>[]).map((s) => ({
          n: s.n ?? null, ok: Boolean(s.ok), got: s.got ?? null,
          ...(s.propagated ? { propagated: true } : {}),
        }))
      : null;
    // For a steps item the correction names the FAILED STEP's expected line
    // (what bank.ts prints in "Corrections:"), not the whole trace — the
    // pattern id is built from wrong/right, and the prose fallback parser
    // reads the same line, so both paths must agree.
    const itemSteps = Array.isArray(item["steps"]) ? (item["steps"] as Record<string, unknown>[]) : [];
    const failStep = itemType === "steps" && graded.failed_step != null
      ? itemSteps.find((s) => s.n === graded.failed_step) ?? null
      : null;
    const right = failStep
      ? (failStep.value && failStep.value !== failStep.expect
          ? `${failStep.expect} = ${failStep.value}`
          : String(failStep.expect ?? ""))
      : correctVersion;
    const record = {
      record_id: `${sessionId}:bank:${Date.now()}`,
      session_id: sessionId,
      ts: Date.now(),
      skill: itemType === "steps" ? "steps" : isMath ? "computation" : vocab ? "vocabulary" : "grammar",
      exercise: String(item.problem ?? item.sentence ?? ""),
      learner_answer: this.lastAnswer.get(sessionId) ?? "",
      score,
      corrections: score >= 8 ? [] : [{
        wrong: isMath ? String(graded.got ?? "") : "",
        right,
        category,
        severity: isMath && verdict !== "near" && verdict !== "empty" ? "critical" : "moderate",
      }],
      competency: competenceId,
      ...(stepTrace ? { steps: stepTrace } : {}),
      // A Review exercise answers a queue item (a failed bank item, or an old
      // error pattern placed in this competence): the record names it, and
      // update-db advances its SM-2 schedule like any reviewed item.
      ...(queueId ? { item_id: queueId, sm2_quality: Math.max(0, Math.min(5, Math.floor(score / 2))) } : {}),
    };
    try {
      const dir = path.join(this.dataDir(), ".records");
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(path.join(dir, `${sessionId}.jsonl`), JSON.stringify(record) + "\n", "utf8");
    } catch {
      /* best-effort, same as the model's own record tool */
    }
  }

  /**
   * One bank answer, credited to today — and, in 🎓 Review, to the lesson.
   *
   * The bank path returns before creditTurn() ever runs, so bank answers never
   * reached the day's count: Go showed ✏️ 0 after twenty exercises (found
   * 2026-09-24). `key` is what was answered, so the same item graded twice in
   * one lesson counts once.
   */
  private creditBankAnswer(sessionId: string, inLesson: boolean, key: string): void {
    try {
      const dir = this.dataDir();
      // 📚 Facts runs on the bank, so its daily counter is bumped here, not in
      // creditTurn (same "only inside that button" rule as `lesson`).
      const inFacts = this.currentCommand.get(sessionId) === "math-vocab";
      bumpDaily(dir, { graded: 1, ...(inLesson ? { lesson: 1 } : {}), ...(inFacts ? { facts: 1 } : {}) });
      this.lastAnswer.delete(sessionId); // one answer, one credit
      if (!inLesson) return;
      const plan = this.lessonPlan();
      const credited = plan.credited ?? [];
      if (credited.includes(`bank:${key}`)) return;
      credited.push(`bank:${key}`);
      plan.credited = credited.slice(-60);
      if (plan.done < plan.total) plan.done += 1;
      writePlan(dir, plan);
      if (plan.done >= plan.total && plan.total > 0) {
        const tally = creditLesson(dir);
        console.log(`[Fluent] 🎓 lesson done (${plan.total} exercises, bank) — ${tally.completed} total`);
      }
    } catch {
      /* the count is a nicety; the answer is not */
    }
  }

  /**
   * 🎓 Review on the bank (PLA-EXERCICIS-TANCATS.md, fase 4): no model at all.
   *
   * The lesson plan and its badge are unchanged; what changes is where each
   * exercise comes from — `curriculum.py bank review-pick`: a failed bank item
   * first, then an old error pattern of the queue placed SAFELY in a
   * competence (option C), then a weak competence. Old patterns that cannot be
   * placed safely are retired from the queue there, with the reason.
   *
   * Returns null to let the model take the turn (no bank item at all): Review
   * then works exactly as before.
   */
  /** A server-authored tutor message (no model): the v2 per-step notes go out
   *  through this, with the same idle/persistence events a bank card emits. */
  private emitBankText(sessionId: string, agent: string, text: string): TurnOutcome {
    const msg = this.createAssistantMessage(sessionId, agent, this.models.deep);
    const part = this.db.insertPart(msg.id, sessionId, { type: "text", text });
    this.emit({ type: "message.part.updated", properties: { part } });
    this.emit({ type: "session.progress", properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) } });
    this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
    this.runAutoPersistence(sessionId);
    const view = () => this.db.getMessageView(msg);
    return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId) };
  }

  /**
   * WP2.5 — one message of a v2 steps exchange. Grades the line against the
   * pending step (hooks/bank.py `grade-step`, i.e. the v1 `_grade_step_line`
   * semantics), advances / retries / reveals per server/src/steps.ts, and on
   * the last step closes the trace (hooks/bank.py `finalize-steps`, which
   * writes progress once — a half-finished exchange records NOTHING, so an
   * abandoned item stays due exactly as it was).
   *
   * "v1" = the learner wrote the WHOLE trace at once (2+ non-blank lines):
   * the deliberate escape hatch — the item falls back to the all-at-once
   * grader unchanged. "error" = the grader could not run; the caller lets the
   * model take the turn rather than grade against a stale guess.
   */
  private stepsV2Grade(
    sessionId: string,
    prev: { competence: string; itemId: string; item?: BankItem; stepsV2?: StepsV2State },
    answerText: string
  ): { kind: "v1" } | { kind: "error" } | { kind: "note"; text: string } | { kind: "final"; graded: Record<string, unknown> } {
    const state = prev.stepsV2;
    const item = prev.item;
    if (!state || !item) return { kind: "v1" };
    const lines = answerText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (lines.length >= 2) {
      delete prev.stepsV2; // "tota la traça de cop": v1 grades it, unchanged
      return { kind: "v1" };
    }
    const step = (item.steps ?? [])[state.stepIdx];
    if (!step) {
      delete prev.stepsV2;
      return { kind: "v1" };
    }
    const g = this.runBankCli([
      "grade-step", "--competence", prev.competence, "--item-id", prev.itemId,
      "--step", String(step.n), "--line", answerText,
    ]);
    const verdict = typeof g?.["verdict"] === "string" ? g["verdict"] : "";
    if (!g || g["error"] || !["correct", "near", "wrong"].includes(verdict)) {
      console.log(`[Fluent] 🏦 session ${sessionId}: v2 grade-step FAILED for ${prev.competence}/${prev.itemId} step ${step.n}`);
      return { kind: "error" };
    }
    const move = stepsV2Handle(item, state, verdict as "correct" | "near" | "wrong", answerText);
    if (!move.done) {
      return { kind: "note", text: stepsV2Note(item, move) };
    }
    const graded = this.runBankCli([
      "finalize-steps", "--competence", prev.competence, "--item-id", prev.itemId,
      "--results", JSON.stringify(state.results),
    ]);
    if (!graded || graded["error"]) {
      console.log(`[Fluent] 🏦 session ${sessionId}: v2 finalize-steps FAILED for ${prev.competence}/${prev.itemId}`);
      return { kind: "error" };
    }
    return { kind: "final", graded };
  }

  private tryBankReviewTurn(sessionId: string, agent: string): TurnOutcome | null {
    let feedback = "";
    let credited: "yes" | "no" | undefined;
    if (this.assignedBankItem.get(sessionId)?.practice === "go") this.assignedBankItem.delete(sessionId);
    const prev = this.assignedBankItem.get(sessionId);
    const answering = this.answerInFront.get(sessionId) === true;

    const lesson = this.lessonState();
    const emit = (text: string) => {
      const msg = this.createAssistantMessage(sessionId, agent, this.models.deep);
      const part = this.db.insertPart(msg.id, sessionId, { type: "text", text });
      this.emit({ type: "message.part.updated", properties: { part } });
      this.emit({ type: "session.progress", properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) } });
      this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
      this.runAutoPersistence(sessionId);
      const view = () => this.db.getMessageView(msg);
      return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId) };
    };

    if (prev && answering) {
      // WP2.5: a v2 steps item is graded one step per message. An intermediate
      // step answer gets a short progress note (no Score marker — the prose
      // persistence fallback stays asleep) and the turn ends there.
      if (prev.stepsV2) {
        const v2 = this.stepsV2Grade(sessionId, prev, this.lastAnswer.get(sessionId) ?? "");
        if (v2.kind === "note") return emit(v2.text);
        if (v2.kind === "error") return null;
        if (v2.kind === "final") {
          // the record's learner_answer is the whole trace, not the last line
          this.lastAnswer.set(sessionId, (prev.stepsV2?.results ?? [])
            .map((r) => String(r.got ?? "")).join("\n"));
          this.appendBankRecord(sessionId, prev.competence, Boolean(prev.vocab), v2.graded, prev.queueId);
          this.creditBankAnswer(sessionId, true, prev.queueId ?? prev.itemId);
          feedback = bankFeedback(v2.graded as unknown as BankGrade) + "\n\n";
          const score = Number(v2.graded["score"] ?? 0);
          credited = score >= KNOWN_SCORE ? "yes" : "no";
          this.assignedBankItem.delete(sessionId);
          console.log(`[Fluent] 🏦 session ${sessionId}: review v2 steps graded ${prev.competence}/${prev.itemId}` +
            `${prev.queueId ? ` (queue ${prev.queueId})` : ""} = ${score}/10`);
        }
      }
      if (!prev.stepsV2) {
        const graded = this.runBankCli([
          "answer", "--competence", prev.competence, "--item-id", prev.itemId,
          "--answer", this.lastAnswer.get(sessionId) ?? "",
        ]);
        if (!graded || graded["error"]) {
          console.log(`[Fluent] 🏦 session ${sessionId}: review grade FAILED for ${prev.competence}/${prev.itemId}`);
          return null;
        }
        this.appendBankRecord(sessionId, prev.competence, Boolean(prev.vocab), graded, prev.queueId);
        this.creditBankAnswer(sessionId, true, prev.queueId ?? prev.itemId);
        feedback = bankFeedback(graded as unknown as BankGrade) + "\n\n";
        const score = Number((graded as Record<string, unknown>)["score"] ?? 0);
        credited = score >= KNOWN_SCORE ? "yes" : "no";
        this.assignedBankItem.delete(sessionId);
        console.log(`[Fluent] 🏦 session ${sessionId}: review graded ${prev.competence}/${prev.itemId}` +
          `${prev.queueId ? ` (queue ${prev.queueId})` : ""} = ${score}/10`);
      }
    }

    if (lesson.total > 0 && lesson.pending <= 0) {
      // Finished: a fixed closing, not a model turn. Pressing Review again on
      // a finished day lands here too, and says so instead of starting over.
      this.assignedBankItem.delete(sessionId);
      return emit(
        feedback +
          `## 🎉 Lesson complete!\n\nYou did all ${lesson.total} exercises of today's review. Well done!\n\n` +
          `Press 🎲 **Go** to keep practicing, or pick a button at the top ` +
          `(🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).`
      );
    }

    // Pressed Review again with an exercise already on screen: show that one
    // again rather than skipping it. A v2 exchange mid-trace re-shows the
    // PENDING STEP, not the opening card (WP2.5).
    const still = this.assignedBankItem.get(sessionId);
    if (still && !answering && still.item) {
      if (still.stepsV2) return emit(stepsV2Resume(still.item, still.stepsV2));
      const card = bankExerciseCard(still.item, lesson.done + 1, difficultyLabel(still.depth ?? "normal"),
        still.name ?? still.competence);
      return emit(card);
    }

    // pacingNote runs before this turn and, on the model lesson path, pre-assigns
    // the next due item (assignedItem) and pushes it into usedItems. On the BANK
    // review path that item is never served — the bank picks its own — so the
    // bank keeps its OWN served list (bankUsedItems): mixing the two made
    // review-pick skip the first due item of every lesson (e0057b4), and with
    // v2's many turns per card even filtering the current pick is not enough
    // (items got skipped, then re-served). The bank's used list holds only
    // queueIds it actually handed out.
    const used = this.bankUsedItems.get(sessionId) ?? [];
    const picked = this.runBankCli(["review-pick", "--used", used.join(","), "--last", prev?.competence ?? ""]);
    const retired = Array.isArray(picked?.["retired"]) ? (picked!["retired"] as unknown[]).length : 0;
    if (retired) console.log(`[Fluent] 🏦 session ${sessionId}: retired ${retired} old queue item(s) with no safe competence`);
    if (!picked || !picked["available"]) {
      console.log(`[Fluent] 🏦 session ${sessionId}: no bank item for review — the model takes this turn`);
      return feedback ? emit(feedback.trim()) : null;
    }
    const item = picked["item"] as BankItem;
    const queueId = (picked["queue_id"] as string | null) ?? null;
    if (queueId && !used.includes(queueId)) used.push(queueId);
    this.bankUsedItems.set(sessionId, used.slice(-60));
    const entry = {
      competence: String(picked["competence"]), itemId: item.id, practice: "review" as const, queueId, item,
      vocab: Boolean(picked["vocab"]), name: String(picked["competence_name"] ?? picked["competence"]),
      depth: String(picked["depth"] ?? "normal"),
      // WP2.5: steps items are served v2 — one step per message. The v1
      // all-at-once grader stays reachable: a first answer with 2+ lines
      // falls back to it (stepsV2Grade), and the e2e "tota la traça de cop"
      // path exercises exactly that.
      stepsV2: item.type === "steps" ? stepsV2Init() : undefined,
    };
    this.assignedBankItem.set(sessionId, entry);
    const card = bankExerciseCard(item, lesson.done + 1, difficultyLabel(entry.depth), entry.name, credited,
      entry.stepsV2 ? "v2" : undefined);
    console.log(`[Fluent] 🏦 session ${sessionId}: review ${picked["source"]} → ${entry.competence}/${item.id}` +
      `${queueId ? ` for ${queueId}` : ""}${entry.stepsV2 ? " (v2)" : ""}`);
    return emit(feedback + card);
  }

  /** Returns a finished TurnOutcome when the assigned competence has a bank
   *  and the turn was fully handled without the model — null to fall through
   *  to the normal (model-driven) path unchanged. */
  private tryBankTurn(sessionId: string, agent: string): TurnOutcome | null {
    // Manual test-only override (never set in production; export it in the
    // shell that runs flowed-start.sh, not in a committed .env): forces every
    // Go/Vocabulary turn in bank mode onto ONE competence, so a pilot bank can
    // be checked on screen without waiting for the normal pacing to pick it.
    // Unset it once the check is done.
    const forced = process.env.FLOWED_BANK_TEST_COMPETENCE;
    const competence = forced ? { ...this.assignedCompetence.get(sessionId), id: forced, name: forced, vocab: forced.includes("vocab") } as AssignedCompetence : this.assignedCompetence.get(sessionId);
    if (!competence) return null;
    // Grade whatever was pending BEFORE deciding whether a next bank item is
    // even available — measured 2026-09-24 (Albert, nes-en): grading pick-gated
    // this way silently dropped an answer when the pick that ran first failed,
    // and the model picked up a turn late, grading the wrong exercise.
    let feedback = "";
    // Same "yes"/"no" flash the model-driven path shows via tagCompetency()
    // (pacing.ts) after grading a turn — the bank path short-circuits before
    // that code ever runs, so without this the comp-tag on a bank exercise
    // never lights up (found 2026-09-24, Albert: 20 bank turns, never green).
    let credited: "yes" | "no" | undefined;
    // An item left on screen by 🎓 Review is not Go's to grade: switching
    // practice drops it (otherwise Go saw "an item still pending" and handed
    // the turn to the model).
    if (this.assignedBankItem.get(sessionId)?.practice === "review") this.assignedBankItem.delete(sessionId);
    const prev = this.assignedBankItem.get(sessionId);
    if (prev && this.answerInFront.get(sessionId) === true) {
      const answerText = this.lastAnswer.get(sessionId) ?? "";
      // WP2.5: v2 steps exchange — one step per message (see stepsV2Grade).
      if (prev.stepsV2) {
        const v2 = this.stepsV2Grade(sessionId, prev, answerText);
        if (v2.kind === "note") return this.emitBankText(sessionId, agent, v2.text);
        if (v2.kind === "error") return null;
        if (v2.kind === "final") {
          this.lastAnswer.set(sessionId, (prev.stepsV2?.results ?? [])
            .map((r) => String(r.got ?? "")).join("\n"));
          this.appendBankRecord(sessionId, prev.competence, Boolean(competence.vocab), v2.graded);
          this.creditBankAnswer(sessionId, false, prev.itemId);
          feedback = bankFeedback(v2.graded as unknown as BankGrade) + "\n\n";
          const score = Number(v2.graded["score"] ?? 0);
          credited = score >= KNOWN_SCORE ? "yes" : "no";
          this.assignedBankItem.delete(sessionId);
          console.log(`[Fluent] 🏦 session ${sessionId}: bank v2 steps graded ${prev.competence}/${prev.itemId} = ${score}/10 (credited=${credited})`);
        }
      }
      if (!prev.stepsV2) {
        const graded = this.runBankCli([
          "answer", "--competence", prev.competence, "--item-id", prev.itemId, "--answer", answerText,
        ]);
        if (!graded || graded["error"]) {
          console.log(`[Fluent] 🏦 session ${sessionId}: bank grade FAILED for ${prev.competence}/${prev.itemId} — ${JSON.stringify(graded)}`);
          return null; // something is off — let the model take this turn rather than drop the answer
        }
        this.appendBankRecord(sessionId, prev.competence, Boolean(competence.vocab), graded);
        this.creditBankAnswer(sessionId, false, prev.itemId);
        feedback = bankFeedback(graded as unknown as BankGrade) + "\n\n";
        const score = Number((graded as Record<string, unknown>)["score"] ?? 0);
        credited = score >= KNOWN_SCORE ? "yes" : "no";
        console.log(`[Fluent] 🏦 session ${sessionId}: bank graded ${prev.competence}/${prev.itemId} = ${score}/10 (credited=${credited})`);
      }
    } else if (prev) {
      // An answer was expected but this turn is not one (e.g. a button press
      // switching away from Go and back, or a retried request). Returning
      // null here used to hand the turn to the model while leaving `prev`
      // assigned — the model then improvised its OWN exercise (often copying
      // the competence's own words, so it looked exactly like a bank card),
      // the learner answered THAT, and the next bank turn graded the answer
      // against the stale `prev` instead — a different item than the one on
      // screen. Seen live 2026-09-24 (Albert, nes-en, a1.vocab_family):
      // card showed "A boy... son" (item .004), graded against item .003
      // ("A girl... daughter") as if "son" were wrong. Re-showing the exact
      // pending card ourselves (same fix already used by 🎓 Review, see
      // `still && !answering` below in tryBankReviewTurn) keeps the card on
      // screen and the pointer in sync — no model turn, no desync.
      console.log(`[Fluent] 🏦 session ${sessionId}: bank turn re-shown (no answer in front, prev=${prev.competence}/${prev.itemId})`);
      if (prev.item && prev.stepsV2) {
        // v2 mid-trace: re-show the pending step, not the opening card.
        return this.emitBankText(sessionId, agent, stepsV2Resume(prev.item, prev.stepsV2));
      }
      if (prev.item) {
        const exerciseNumber = this.gradedSoFar(sessionId).count + 1;
        const card = bankExerciseCard(
          prev.item, exerciseNumber, difficultyLabel(prev.depth ?? "normal"), prev.name ?? competence.name
        );
        const msg = this.createAssistantMessage(sessionId, agent, this.models.deep);
        const part = this.db.insertPart(msg.id, sessionId, { type: "text", text: card });
        this.emit({ type: "message.part.updated", properties: { part } });
        this.emit({ type: "session.progress", properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) } });
        this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
        this.runAutoPersistence(sessionId);
        const view = () => this.db.getMessageView(msg);
        return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId) };
      }
      // No stored item (session from before this fix): fall back to the old
      // behaviour rather than crash — the model takes this one turn.
      return null;
    }

    const picked = this.runBankCli(["pick", "--competence", competence.id]);
    if (!picked || !picked["available"]) {
      console.log(`[Fluent] 🏦 session ${sessionId}: bank pick unavailable for ${competence.id} — ${JSON.stringify(picked)}`);
      return null;
    }
    const item = picked["item"] as BankItem;

    const exerciseNumber = this.gradedSoFar(sessionId).count + 1;
    // WP2.5: steps items go v2 (one step per message) in Go too — same
    // dispatch as 🎓 Review; the multi-line first answer escapes to v1.
    const stepsV2 = item.type === "steps" ? stepsV2Init() : undefined;
    const card = bankExerciseCard(
      item, exerciseNumber, difficultyLabel(String(picked["depth"] ?? "normal")), competence.name, credited,
      stepsV2 ? "v2" : undefined
    );
    this.assignedBankItem.set(sessionId, {
      competence: competence.id, itemId: item.id, practice: "go", item, name: competence.name,
      depth: String(picked["depth"] ?? "normal"), stepsV2,
    });

    const msg = this.createAssistantMessage(sessionId, agent, this.models.deep);
    const part = this.db.insertPart(msg.id, sessionId, { type: "text", text: feedback + card });
    this.emit({ type: "message.part.updated", properties: { part } });
    this.emit({ type: "session.progress", properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) } });
    // session.idle → incremental persistence (accumulate-session.py), same as
    // the model-driven path (executeTurn, below). Missing here meant a bank
    // answer landed correctly in .records/<sessionId>.jsonl (appendBankRecord
    // mirrors the math_record_answer shape) but mastery-db.json — the store
    // accumulate-session.py -> update-db.py actually writes competence mastery
    // to — was never touched, so the global "% competences known" stat never
    // moved no matter how many bank exercises were answered (found 2026-09-24,
    // Albert: 20 bank answers, stat unchanged).
    this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
    this.runAutoPersistence(sessionId);
    const view = () => this.db.getMessageView(msg);
    return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId) };
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

    // How many answers were on record BEFORE this turn. The counter used to be
    // read only from the tutor's "Score: N/10"; a tutor that calls
    // math_record_answer and forgets the sentence then graded nothing as far
    // as the server knew. Measured: four structured records, counter at 0 of 12.
    const recordsBefore = this.recordCount(sessionId);

    // Pacing: appended to what the model sees, never persisted into the
    // learner's own message.
    const note = this.pacingNote(sessionId);
    this.logNote(sessionId, note);

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

    // Offline bank (PLA-EXERCICIS-TANCATS.md): when the competence this turn
    // is about has a validated bank, the server picks, paints and corrects
    // the exercise itself — no model call for the exercise at all. Only for
    // Go/Vocabulary (math-learn/math-vocab); a competence without a bank
    // falls straight through to the path below, unchanged.
    if (this.bankEnabled() && (this.currentCommand.get(sessionId) === "math-learn" || this.currentCommand.get(sessionId) === "math-vocab")) {
      const bankOutcome = this.tryBankTurn(sessionId, agent);
      if (bankOutcome) return bankOutcome;
    }
    // 🎓 Review on the bank too (fase 4). Same switch; null = the model path, as before.
    if (this.bankEnabled() && this.currentCommand.get(sessionId) === "math-review") {
      const reviewOutcome = this.tryBankReviewTurn(sessionId, agent);
      if (reviewOutcome) return reviewOutcome;
    }

    // The stall warning is about the LESSON not advancing — and it only means
    // anything on a turn the MODEL answers. The bank paths above return before
    // this line: they advance the lesson deterministically, and a note that
    // stays identical across bank turns is the normal shape of a finished plan
    // re-serving a weak card (seen live on test-m7, WP1.1-live: four identical
    // "lesson is COMPLETE" notes while the bank served and graded
    // m7.factor_letters.001 — the lesson was advancing fine). Free practice's
    // note is a list of what she already knows, and it legitimately stays the
    // same for as long as nothing new is answered correctly.
    if (note) {
      const prev = this.noteStall.get(sessionId);
      const turns = prev && prev.note === note ? prev.turns + 1 : 1;
      this.noteStall.set(sessionId, { note, turns });
      if (this.noteStall.size > 500) this.noteStall.clear();
      if (turns === 4 && this.currentCommand.get(sessionId) === "math-review") {
        console.log(
          `[Fluent] ⚠ session ${sessionId}: the pacing note has not changed in 4 turns — ` +
            `the lesson is not advancing. Note: ${note.slice(0, 120)}`
        );
      }
    }

    if (note) history = [...history, { role: "system", content: note }];

    const { model } = await resolveModel(agent, this.models);
    const msg = this.createAssistantMessage(sessionId, agent, model);
    const view = () => this.db.getMessageView(msg);

    // Streaming (FLOWED_STREAM=1): the first delta creates an empty text part,
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

    // A part emitted here reaches the browser immediately — but enforceTurn,
    // below, has not run yet, and it rewrites a wrong exercise in place about
    // as often as not (repeats, ungraded turns, unanchored blanks). Measured
    // live, 2026-09-22 (Albert): the flawed exercise really was shown for the
    // 2-4s enforceTurn takes, then silently swapped for the fixed one — not
    // just a log artifact. With streaming off (FLOWED_STREAM unset, the
    // config this app actually runs), nothing is lost by holding the text
    // part back until enforceTurn has had its say: it is inserted here (so
    // enforceTurn can still find and rewrite it) but NOT emitted; the emit
    // happens once, after enforceTurn returns, from whatever view() shows at
    // that point — the rewritten text if there was one, the original
    // otherwise. Tool-call parts still emit immediately (never guarded).
    //
    // This does NOT cover FLOWED_STREAM=1: onDelta below emits the first
    // token as soon as it arrives, by design, so the learner watches it being
    // typed — holding that back would mean no live streaming at all, a
    // separate trade-off this does not make on its own. In a streaming
    // environment the same flash-then-swap would still happen; ask before
    // turning streaming on if that matters there.
    const heldTextPartIds: string[] = [];
    let recordArgs: Record<string, unknown> | null = null;
    const onPart = (step: TurnPart) => {
      if (step.kind === "tool") {
        flushStream(); // close any text the model streamed before calling a tool
        const t = step as ToolStep;
        if (t.name === "math_record_answer" && t.args && typeof t.args === "object") {
          recordArgs = t.args as Record<string, unknown>;
        }
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
        streamText = this.tidyTutorText(sessionId, step.text);
        flushStream();
        return;
      }
      const part = this.db.insertPart(msg.id, sessionId, {
        type: "text",
        text: this.tidyTutorText(sessionId, step.text),
      });
      heldTextPartIds.push(part.id);
    };
    // Emits each held part's CURRENT row (view() re-read fresh each time, so
    // a rewrite already applied by enforceTurn is what goes out, never the
    // stale pre-rewrite text) — called once, after the turn is fully settled.
    const emitHeld = () => {
      for (const id of heldTextPartIds) emitPart(id);
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
          emitHeld();
          return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId, retry.metrics?.promptTokens) };
        } catch (e2) {
          e = e2;
        }
      }
      flushStream();
      emitHeld(); // any text produced before the error still reaches the learner
      const text = `⚠️ ${e instanceof Error ? e.message : String(e)}`;
      this.db.insertPart(msg.id, sessionId, { type: "text", text });
      this.emit({ type: "message.part.updated", properties: { part: view().parts.at(-1) } });
      this.emit({ type: "session.error", properties: { sessionID: sessionId, error: { message: text } } });
    }

    await this.enforceTurn(sessionId, msg.id, view, system, history, tools, model, onPart, onDelta);
    this.repairShownText(sessionId, msg.id, view, recordArgs, heldTextPartIds);
    emitHeld();

    this.logTurn(sessionId, agent, model.name, startedAt, history, metrics);

    // Credit the answer just graded, to the DAY. The score marker is in the
    // tutor's text whether or not it remembered the tool call, so the counter
    // moves either way — which is the whole reason it is read from here.
    this.creditTurn(sessionId, view().parts, recordsBefore);

    // Where the learner is now. Emitted after persistence so the count includes
    // the answer just graded.
    this.emit({
      type: "session.progress",
      properties: { sessionID: sessionId, ...this.sessionProgress(sessionId) },
    });

    // session.idle → incremental persistence (accumulate-session.py)
    this.emit({ type: "session.idle", properties: { sessionID: sessionId } });
    this.runAutoPersistence(sessionId);

    // The session itself has gone past reliable use — not one bad exercise,
    // the model no longer doing the one thing every turn must do (grade) or
    // the context already having needed real turns cut to fit. Bounced once,
    // never twice for the same session (see `bounced`): the frontend starts a
    // clean one, and a session that is unlucky right after that is a new
    // problem, not this one repeating.
    if (!this.bounced.has(sessionId)) {
      const reason = bounceReason({
        historyDropped: pruned.dropped > 0,
        ungradedStreak: this.ungradedStreak.get(sessionId) ?? 0,
      });
      if (reason) {
        this.bounced.add(sessionId);
        if (this.bounced.size > 500) this.bounced.clear();
        console.log(`[Fluent] ⟲ session ${sessionId}: bouncing (${reason})`);
        this.emit({ type: "session.bounce", properties: { sessionID: sessionId, reason } });
      }
    }

    return { info: view().info, parts: view().parts, debug: this.debugStatus(sessionId, metrics?.promptTokens) };
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

  /**
   * How many records this session's file actually holds. No fallback.
   *
   * `gradedSoFar()` deliberately falls back to counting the tutor's score lines
   * when there is no records file, because the learner's progress indicator
   * must not depend on a tool call. That fallback made it useless for the one
   * question that needs a straight answer — *did the tool write anything?* —
   * and the derived-record path, which asked exactly that, never fired once.
   */
  private recordCount(sessionId: string): number {
    try {
      const file = path.join(this.dataDir(), ".records", `${sessionId}.jsonl`);
      return fs.readFileSync(file, "utf8").split("\n").filter((l) => l.trim()).length;
    } catch {
      return 0;
    }
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
  private creditTurn(sessionId: string, parts: Record<string, unknown>[], recordsBefore = -1): void {
    try {
      const text = parts
        .filter((p) => (p as { type?: string }).type === "text")
        .map((p) => String((p as { text?: string }).text ?? ""))
        .join("\n");

      // What was asked this turn — tracked in every practice, not only the
      // Lesson, because the loop we are guarding against is not specific to it.
      const asked = exerciseFingerprints(text);
      // Was the exercise on screen the one the server assigned a competence for?
      //
      // Used to also require followsCompetence(comp, text) — a signal-word match
      // against the VISIBLE exercise text. That breaks exactly when the blank hides
      // the signal word itself: "___ is your favorite subject?" never shows "what"
      // anywhere on screen, so a1.question_words could never pass it. Measured live,
      // 2026-09-23 (nes-en): a1.question_words and a1.have_got answers went unlabeled
      // turn after turn, hooks/curriculum.py's daily quota for them never filled (no
      // competency = uncounted, and neither has a Words: list to fall back on), and
      // review_pool kept re-picking the same two weakest competences for 20+ turns.
      // turnGuard() (pacing.ts) already rejects and forces a rewrite of an exercise
      // that drifted off the assigned competence, before this ever runs — so by the
      // time creditTurn sees the text, trusting that an exercise was actually shown
      // under this assignment is enough; the extra visible-text check only produced
      // false negatives here.
      {
        const comp = this.assignedCompetence.get(sessionId);
        if (comp) {
          comp.shown = asked.length > 0;
          comp.followed = comp.shown;
        }
      }
      // What the learner was answering: the exercise that was on screen BEFORE
      // this turn. Captured before lastAsked is overwritten below.
      const answered = (this.lastAsked.get(sessionId) ?? [])[0];
      const answeredAll = [...(this.lastAsked.get(sessionId) ?? [])];
      if (asked.length) {
        const prev = this.lastAsked.get(sessionId) ?? [];
        if (prev.length && asked.every((a) => prev.includes(a))) {
          console.log(
            `[Fluent] ↻ session ${sessionId}: same exercise twice in a row ("${asked[0]}")`
          );
          this.logGuard(sessionId, `repeated in a row: ${asked[0]}`, text);
        }
        this.lastAsked.set(sessionId, asked);
        if (this.lastAsked.size > 500) this.lastAsked.clear();
      }

      // Remember what she has ANSWERED CORRECTLY today, in EVERY practice: that is
      // what must not come back. It used to be everything that had been shown,
      // which also banned an exercise she walked away from (fine to show again)
      // and one she got wrong (SM-2 wants it back). The exercise just answered
      // is the one on screen BEFORE this reply, and the score is in this reply.
      {
        const prevAsked = answeredAll;
        const score = scoreOfReply(text);
        if (
          this.answerInFront.get(sessionId) === true &&
          prevAsked.length &&
          score !== null &&
          score >= KNOWN_SCORE
        ) {
          const key = `${sessionId}|${this.currentCommand.get(sessionId) ?? "-"}`;
          const here = this.askedByPractice.get(key) ?? [];
          for (const label of prevAsked) if (!here.includes(label)) here.push(label);
          this.askedByPractice.set(key, here.slice(-40));
          if (this.askedByPractice.size > 500) this.askedByPractice.clear();
          const plan = this.lessonPlan();
          const before = plan.covered.length;
          for (const label of prevAsked) {
            if (!plan.covered.includes(label)) plan.covered.push(label);
          }
          if (plan.covered.length > 40) plan.covered = plan.covered.slice(-40);
          if (plan.covered.length !== before) writePlan(this.dataDir(), plan);
        }
      }

      // Two witnesses that an answer was graded, and the structured one is the
      // better: a tool call is a fact, a sentence is a formatting habit. Either
      // is enough. Requiring the sentence alone froze Iona's lesson at 0 of 12
      // while she worked through thirteen exercises.
      const gradedNow =
        countGradedInText([text]) > 0 ||
        (recordsBefore >= 0 && this.recordCount(sessionId) > recordsBefore);

      // Real exercises, not a synthetic probe: an answered turn that produced no
      // grade at all is the model failing at the one thing every turn must do.
      // Two in a row is the signal (see bounceReason) — never counted for a
      // button turn, which has nothing to grade in the first place.
      if (this.answerInFront.get(sessionId) === true) {
        const streak = gradedNow ? 0 : (this.ungradedStreak.get(sessionId) ?? 0) + 1;
        this.ungradedStreak.set(sessionId, streak);
        if (this.ungradedStreak.size > 500) this.ungradedStreak.clear();
      }

      if (!gradedNow) return;

      // Grading with nobody having answered is not grading. A turn opened by a
      // BUTTON — 🎓 Lesson, 📚 Vocabulary — carries no answer, and when the
      // tutor decorated its opening reply with a "Score: 2/10" the server
      // credited an exercise nobody had been asked yet: the plan came out
      // `done: 1, credited: []` before the first question. Measured
      // 2026-09-19; in the rig it aborted four of six executions, and for a
      // learner it silently costs her an exercise at the top of every lesson.
      if (!(this.lastAnswer.get(sessionId) ?? "").trim()) {
        console.log(
          `[Fluent] ↻ session ${sessionId}: a score with no answer behind it — not counted`
        );
        this.logGuard(sessionId, "graded with no answer", text);
        return;
      }

      // The tutor graded in prose and did not call math_record_answer — the
      // usual case, measured across three live lessons: six good corrections,
      // zero calls, and nothing at all reaching the databases. Everything the
      // call would have carried is already in the text, because the learner had
      // to read it. So take it from there.
      if (recordsBefore >= 0 && this.recordCount(sessionId) === recordsBefore) {
        // `answeredAll` was captured above, BEFORE `this.lastAsked` was
        // overwritten with the exercise this same reply just asked next —
        // that overwrite already happened a few lines up. deriveRecord must
        // not read `this.lastAsked` itself: by the time it runs it would get
        // the NEW exercise, not the one this answer was actually for.
        // Measured 2026-09-22: "I ___ (swim)..." recorded against the answer
        // "are", which was for the PREVIOUS exercise ("There ___ a lot of
        // people...") — every derived record was one exercise off.
        this.deriveRecord(sessionId, text, answeredAll);
      }

      const inLesson = this.currentCommand.get(sessionId) === "math-review";
      // Same principle as `lesson`: only credited while that specific button's
      // flow is the active one, never by an equivalent exercise mix happens to
      // surface on its own — a daily "did you also do one of these" reminder,
      // not a gate (2026-09-22, Albert).
      const inReasoning = this.currentCommand.get(sessionId) === "math-writing";
      const inProblems = this.currentCommand.get(sessionId) === "math-reading";
      const inFacts = this.currentCommand.get(sessionId) === "math-vocab";
      const dir = this.dataDir();
      bumpDaily(dir, {
        graded: 1,
        ...(inLesson ? { lesson: 1 } : {}),
        ...(inReasoning ? { reasoning: 1 } : {}),
        ...(inProblems ? { problems: 1 } : {}),
        ...(inFacts ? { facts: 1 } : {}),
      });
      // One answer, one credit. Consumed here so that a later turn with no
      // answer of its own — a button, a second assistant message in the same
      // tool loop — cannot count this one again.
      this.lastAnswer.delete(sessionId);

      if (inLesson) {
        const plan = this.lessonPlan();
        // One credit per exercise. The tutor that graded "xxx", "banana" and
        // "zzz" against the same single question six times over drove the badge
        // to 6 of 6 with one exercise asked. An unidentifiable exercise still
        // counts, so a fingerprinting miss can never cost the learner progress.
        const credited = plan.credited ?? [];
        if (answered && credited.includes(answered)) {
          // Not an anomaly: the guard doing its job, and it belongs with the
          // other guard events rather than in the warning channel. ⚠ is for
          // something wrong that nobody is fixing; this is something wrong
          // being fixed.
          console.log(`[Fluent] ↻ session ${sessionId}: "${answered}" already counted — not twice`);
          this.logGuard(sessionId, `already counted: ${answered}`, text);
          return;
        }
        if (answered) {
          credited.push(answered);
          plan.credited = credited.slice(-60);
        }
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

  /** Is this id really in the learner's queue? The tool validates the same
   *  thing before it writes; a derived record has no other referee. */
  private itemExists(id: string): boolean {
    try {
      const sr = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "spaced-repetition.json"), "utf8")
      );
      return Boolean(sr?.items && Object.prototype.hasOwnProperty.call(sr.items, id));
    } catch {
      return false;
    }
  }

  /** One line per guard event, beside the turn metrics.
   *
   *  The server log lives in /tmp and is gone by the time anyone asks what
   *  happened; the profile is where the evidence has to be, next to the turn it
   *  belongs to. Twice a run has been argued about because nobody could see
   *  whether the guard had fired. */
  private logGuard(sessionId: string, note: string, text: string): void {
    try {
      const dir = path.join(this.dataDir(), ".metrics");
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(
        path.join(dir, "guards.jsonl"),
        JSON.stringify({ ts: Date.now(), session: sessionId,
                         note: note.slice(0, 160), head: text.slice(0, 1500) }) + "\n",
        "utf8"
      );
    } catch {
      /* best-effort */
    }
  }

  /** What the server told the tutor this turn, next to what the learner said.
   *
   *  The guard and the note can contradict each other ("this item is the next
   *  exercise" vs "a DIFFERENT exercise"), and the only way to tell is to read
   *  both for the same turn. Kept apart from guards.jsonl on purpose: it is
   *  not an intervention, and mixing them would inflate every guard count. */
  private logNote(sessionId: string, note: string | null): void {
    try {
      const dir = path.join(this.dataDir(), ".metrics");
      fs.mkdirSync(dir, { recursive: true });
      const item = this.assignedItem.get(sessionId);
      const comp = this.assignedCompetence.get(sessionId);
      fs.appendFileSync(
        path.join(dir, "notes.jsonl"),
        JSON.stringify({
          ts: Date.now(),
          session: sessionId,
          command: this.currentCommand.get(sessionId) ?? null,
          answer: (this.lastAnswer.get(sessionId) ?? "").slice(0, 80),
          assigned: item ? { id: item.id, content: item.content } : null,
          competence: comp ? { id: comp.id, name: comp.name, kind: comp.kind ?? null } : null,
          last_asked: this.lastAsked.get(sessionId) ?? [],
          note: note ? note.slice(0, 2000) : null,
        }) + "\n",
        "utf8"
      );
    } catch {
      /* best-effort */
    }
  }

  /**
   * After the guards, one thing the learner must never be left with
   * (tutor-bench, 2026-09-27 — docs/MODELBENCH.md): an answer graded in
   * math_record_answer with nothing of it on screen ("Waiting for your
   * answer! ⏱️") — the feedback is rebuilt from the call and put before
   * whatever the reply says.
   */
  private repairShownText(
    sessionId: string,
    messageId: string,
    view: () => { parts: unknown[] },
    recordArgs: Record<string, unknown> | null,
    heldTextPartIds: string[],
  ): void {
    try {
      const texts = view().parts.filter((p) => (p as { type?: string }).type === "text") as Array<{ id?: string; text?: string }>;
      // WP5.2: language domain — drop characters of a script the learner cannot
      // read (14B, Reading, 2026-09-27: "swings, 滑梯, and…" in an A1 text).
      if (this.domainForSession() === "language") {
        const langs = this.learnerLanguages();
        for (const p of texts) {
          const t = String(p.text ?? "");
          if (p.id && foreignScript(t, langs.target, langs.native)) {
            this.db.updatePart(String(p.id), { type: "text", text: stripForeignScript(t, langs.target, langs.native) });
            this.logGuard(sessionId, "foreign script dropped", t);
          }
        }
      }
      if (!recordArgs || this.answerInFront.get(sessionId) !== true) return;
      const shown = view().parts.some((p) => {
        const q = p as { type?: string; text?: string };
        return q.type === "text" && scoreOfReply(String(q.text ?? "")) !== null;
      });
      if (shown) return;
      const feedback = feedbackFromRecord(recordArgs);
      if (!feedback) return;
      const last = [...texts].reverse().find((p) => p.id);
      if (last?.id) {
        const now = view().parts.find((p) => (p as { id?: string }).id === last.id) as { text?: string } | undefined;
        const body = String(now?.text ?? "");
        this.db.updatePart(String(last.id), { type: "text", text: `${feedback}\n\n${body}`.trim() });
      } else {
        const part = this.db.insertPart(messageId, sessionId, { type: "text", text: feedback });
        heldTextPartIds.push(part.id);
      }
      this.logGuard(sessionId, "feedback rebuilt from math_record_answer", feedback);
    } catch (e) {
      console.log(`[Fluent] repairShownText failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  /** The two things the server knows better than the tutor: what the score
   *  means, and where the lesson actually is. */
  private tidyTutorText(sessionId: string, text: string): string {
    // The model's own reasoning, when it leaks: a whole <think>…</think> block or a
    // lone "</think>" (seen on a Writing exercise, on the learner's screen).
    const clean = stripCompetencyLeak(
      String(text ?? "")
        .replace(/<think>[\s\S]*?<\/think>\s*/gi, "")
        .replace(/<\/?think>\s*/gi, "")
    );
    const aligned = alignMarkersToScore(stripTemplateBraces(clean));
    const command = this.currentCommand.get(sessionId);
    // Debug aid, not for the learner: barely-visible tag of which competence
    // this exercise was built for, so the rotation (the thing that was silently
    // broken — see followsCompetence, 2026-09-22) can be watched live on the
    // page instead of only after the fact in the records. Only where the
    // curriculum actually assigns a competence (see pacingNote/curriculumNoteFor).
    const assignedComp =
      command === "math-learn" || command === "math-vocab"
        ? this.assignedCompetence.get(sessionId)
        : null;
    // Same check as recordCompetence() (which runs later, off this exact map
    // entry) — computed here so the tag can show it the moment the reply
    // grading THIS exercise is rendered, not only after creditTurn writes the
    // record. gradingCompetence already carries whatever last turn's
    // creditTurn set on .followed; vocab is excluded because Python resolves
    // those by word match, not by this flag, so "no" here would be a false
    // alarm for it.
    const grading = this.gradingCompetence.get(sessionId);
    const credited: "yes" | "no" | "na" =
      !grading || grading.vocab ? "na" : grading.followed ? "yes" : "no";
    const out = assignedComp ? tagCompetency(aligned, assignedComp.id, credited) : aligned;
    if (command === "math-review") {
      try {
        const lesson = this.lessonWithAnswerInFront(sessionId);
        return alignLessonHeader(out, lesson.done, lesson.total);
      } catch {
        return out;
      }
    }
    // Free practice (Go, Speaking...) has no total to count down to — just a
    // running number the model is supposed to keep in its own head. Vocabulary
    // has its own "{N}/{total}" template and is left to it. See exerciseSeq.
    if (command && command !== "math-vocab" && hasExerciseHeader(out)) {
      try {
        const key = `${sessionId}|${command}`;
        const n = (this.exerciseSeq.get(key) ?? 0) + 1;
        this.exerciseSeq.set(key, n);
        if (this.exerciseSeq.size > 500) this.exerciseSeq.clear();
        return alignExerciseNumber(out, n);
      } catch {
        return out;
      }
    }
    return out;
  }

  /**
   * Make the tutor write the turn again when the turn does not move the lesson.
   *
   * Once. Never twice: a second failure is a tutor that cannot do it today, and
   * a loop here costs the learner a minute of staring at nothing. If the retry
   * is no better, the first reply stands — a flawed exercise beats a blank
   * screen, and the log says what happened.
   */
  private async enforceTurn(
    sessionId: string,
    messageId: string,
    view: () => { info: unknown; parts: Record<string, unknown>[] },
    system: string,
    history: ChatMsg[],
    tools: ToolDefinition[],
    model: ModelConfig,
    onPart: Parameters<typeof runTurn>[5],
    onDelta: Parameters<typeof runTurn>[7]
  ): Promise<void> {
    try {
      const parts = view().parts;
      const last = [...parts].reverse().find((p) => (p as { type?: string }).type === "text") as
        | { id?: string; text?: string }
        | undefined;
      const text = String(last?.text ?? "");
      if (!last?.id || !text.trim()) return;

      const inLesson = this.currentCommand.get(sessionId) === "math-review";
      const lesson = this.lessonWithAnswerInFront(sessionId);
      const graded = scoreOfReply(text);
      const justKnown =
        this.answerInFront.get(sessionId) === true && graded !== null && graded >= KNOWN_SCORE
          ? (this.lastAsked.get(sessionId) ?? [])
          : [];
      // Snapshot now: the "already asked" branch below calls pacingNote()
      // again mid-turn, which reassigns this.assignedCompetence to whatever
      // curriculum.py picks next. The exercise text that ends up on screen
      // (kept via splice when only the feedback needed a rewrite) is still
      // the ORIGINAL exercise, so the guard below must judge it against the
      // competence that was actually assigned when it was written — not
      // whatever the map holds by the time this runs. Measured 2026-09-22:
      // a reassignment to vocab_numbers mid-turn made openBlankGuard patch
      // "Number: one" into an unrelated articles_plurals exercise that had
      // nothing to do with numbers.
      const compAtStart = this.assignedCompetence.get(sessionId) ?? null;
      // WP5.2: the language-domain guards (domain-language.ts) run only for a
      // language profile; a math profile pays nothing (langs stays null).
      const langs = this.domainForSession() === "language" ? this.learnerLanguages() : null;
      const note = (langs ? foreignScriptGuard(text, langs.target, langs.native) : null)
        ?? pictureGuard(text)
        ?? writingBlankGuard(text, this.currentCommand.get(sessionId))
        ?? reasoningTaskGuard(text, this.currentCommand.get(sessionId))
        ?? wordProblemTaskGuard(text, this.currentCommand.get(sessionId))
        ?? (langs ? languageDirectionGuard(text, langs.target, langs.native) : null)
        ?? turnGuard({
        inLesson,
        pending: lesson.pending,
        // What she has answered correctly — plus the exercise this very reply is
        // grading, when it grades it as known: creditTurn has not run yet, and
        // showing the exercise she just got right straight away is the repeat.
        coveredToday: [...this.lessonPlan().covered, ...justKnown],
        askedHere: [
          ...(this.askedByPractice.get(
            `${sessionId}|${this.currentCommand.get(sessionId) ?? "-"}`
          ) ?? []),
          ...justKnown,
        ],
        asked: exerciseFingerprints(text),
        graded: countGradedInText([text]) > 0,
        closing: /session complete|review session complete/i.test(text),
        due: lesson.due,
        replyText: text,
        oneAtATime: this.currentCommand.get(sessionId) === "math-vocab",
        buttonTurn: this.answerInFront.get(sessionId) === false,
        assigned: inLesson ? this.assignedItem.get(sessionId) ?? null : null,
        competence: inLesson ? null : compAtStart,
        grading: inLesson && this.answerInFront.get(sessionId) === true
          ? this.gradingItem.get(sessionId) ?? null
          : null,
        answerText: this.lastAnswer.get(sessionId) ?? null,
        answering:
          this.answerInFront.get(sessionId) === true
            ? (this.lastAsked.get(sessionId) ?? [])[0] ?? null
            : null,
      });
      if (!note) return;

      console.log(`[Fluent] ↻ session ${sessionId}: ${note.slice(0, 80)}…`);
      this.logGuard(sessionId, note, text);
      // The rewrite starts from scratch, and a model told only "ask the next card"
      // picks the one it just asked (measured: "llibre" answered 10/10, then asked
      // again by the rewrite of the very next turn). Say which ones are off limits.
      const avoid = [
        ...new Set([...this.lessonPlan().covered, ...justKnown].map((a) => String(a).trim()).filter(Boolean)),
      ];
      const exerciseOnly = isExerciseGuard(note);
      // The mirror case: the exercise on screen is fine and the feedback is what is
      // missing. Rewriting the whole turn made the model grade the NEXT card.
      const gradingNow =
        inLesson && this.answerInFront.get(sessionId) === true
          ? this.gradingItem.get(sessionId) ?? null
          : null;
      const feedbackOnly = isFeedbackGuard(note) && trailingExercise(text) !== null;
      const retryNote =
        (avoid.length > 0 && !/already asked/i.test(note)
          ? `${note} Not any of these — she already got them right today: ${avoid
              .slice(-40)
              .map((a) => `"${a}"`)
              .join(", ")}.`
          : note) +
        (exerciseOnly
          ? ` The feedback already shown stays exactly as it is: write ONLY the next exercise — ` +
            `no feedback, no correction, no score.`
          : feedbackOnly
            ? ` The next exercise is already on screen and stays as it is: write ONLY the feedback on ` +
              `the learner's answer — the verdict, "Correct version:" and "**Score: N/10**" — and stop ` +
              `after the score line. No new exercise.`
            : ``);
      // "Already asked" repeats happen because the pacing note baked into
      // `history` (computed once, at the top of the turn) still points at the
      // exact item/competence the model just repeated — telling it "write
      // something different" while it is still staring at the same assignment
      // rarely works on a small model. Re-deriving the assignment here picks a
      // fresh one: pacingNote's review branch already records the item it hands
      // out as used the moment it is chosen, so calling it again now (that item
      // already marked used) naturally returns a different one. Measured
      // 2026-09-22: Question 13 repeated Question 12 verbatim, guard fired and
      // forced a rewrite, rewrite repeated it again anyway — this is that fix.
      let retryHistory = history;
      if (/already asked/i.test(note)) {
        // pacingNote() -> curriculumNoteFor() always re-snapshots gradingCompetence
        // from whatever assignedCompetence holds RIGHT NOW -- but at this point in
        // the turn that is the competence assigned for the exercise this retry is
        // about to replace, not yet .shown/.followed (creditTurn has not run yet).
        // Calling it again here would clobber the correct snapshot -- the PREVIOUS
        // turn's competence, already graded and credited -- with this incomplete
        // one, and the record for what she actually just answered loses its
        // competency. Measured 2026-09-23 (ses_28777e): this is why competency
        // stayed null even after comp.followed = comp.shown, and why the same
        // competence got assigned twice in a row in notes.jsonl -- the retry's
        // reassignment is real and wanted (a fresh note for the rewrite), only the
        // gradingCompetence side-effect of getting there needs undoing.
        const savedGrading = this.gradingCompetence.get(sessionId);
        const fresh = this.pacingNote(sessionId);
        if (savedGrading) this.gradingCompetence.set(sessionId, savedGrading);
        else this.gradingCompetence.delete(sessionId);
        if (fresh) {
          const idx = retryHistory.map((m) => m.role).lastIndexOf("system");
          retryHistory =
            idx === -1
              ? [...retryHistory, { role: "system", content: fresh }]
              : [...retryHistory.slice(0, idx), { role: "system", content: fresh }, ...retryHistory.slice(idx + 1)];
        }
      }
      const retry = await runTurn(
        model,
        system,
        [...retryHistory, { role: "assistant", content: text }, { role: "system", content: retryNote }],
        tools, 3,
        () => {
          /* the retry's parts are not persisted separately: it replaces the text */
        },
        { sessionID: sessionId, messageID: messageId, dataDir: this.dataDir() },
        () => {
          /* no streaming on a retry: the learner already saw nothing */
        }
      );
      let better = alignMarkersToScore(String(retry.text ?? "").trim());
      if (!better) return;
      // A rewrite that drops the correction is worse than the repetition it was
      // meant to fix: the learner loses her feedback to gain a different
      // question. Measured — nine rewrites in three runs, and the marker and the
      // correct version gone from a third of the replies.
      let spliced = false;
      if (feedbackOnly) {
        const merged = mergeFeedbackOnly(text, better, gradingNow);
        if (!merged) {
          console.log(`[Fluent] ↻ session ${sessionId}: the feedback rewrite is unusable — keeping the first reply`);
          this.logGuard(sessionId, "rewrite rejected: feedback lost", better);
          return;
        }
        better = alignMarkersToScore(merged);
        spliced = true;
      }
      if (exerciseOnly) {
        // Keep the first reply's feedback and take only the exercise from the
        // rewrite: a whole new turn grades the answer the learner has not given.
        const only = exerciseOnlyOf(better);
        const merged = only ? spliceFeedback(text, only) : null;
        if (merged) {
          better = alignMarkersToScore(merged);
          spliced = true;
        }
      }
      const MARK = /[🟢🟡🔴✅❌]/u;
      const lostVersion = text.includes("Correct version:") && !better.includes("Correct version:");
      const lostMarker = MARK.test(text) && !MARK.test(better);
      if (!spliced && (lostVersion || lostMarker)) {
        // The rewrite is usually just the next exercise. The feedback is in the
        // first reply: put the two together instead of throwing the exercise away.
        const merged = spliceFeedback(text, better);
        if (merged) {
          better = alignMarkersToScore(merged);
          spliced = true;
        }
      }
      if (!spliced && (lostVersion || lostMarker)) {
        console.log(
          `[Fluent] ↻ session ${sessionId}: the rewrite lost the feedback — keeping the first reply`
        );
        this.logGuard(sessionId, "rewrite rejected: feedback lost", better);
        return;
      }
      this.db.updatePart(String(last.id), { type: "text", text: better });
      this.emit({
        type: "message.part.updated",
        properties: { part: view().parts.find((p) => (p as { id?: string }).id === last.id) },
      });
      console.log(`[Fluent] ↻ session ${sessionId}: turn rewritten`);
      this.logGuard(sessionId, spliced ? "rewritten (feedback kept, exercise replaced)" : "rewritten", better);
    } catch (e) {
      console.log(
        `[Fluent] ↻ session ${sessionId}: guard failed, keeping the first reply ` +
          `(${e instanceof Error ? e.message : String(e)})`
      );
    }
  }

  /**
   * Write the record the tutor should have called `math_record_answer` for.
   *
   * Only ever a fallback: a real tool call always wins, because it carries the
   * item_id and this cannot (the id is the tutor's to know, and guessing one
   * would corrupt the review schedule). What this does recover is the part that
   * was being lost completely — the score, the corrections and the categories
   * that mistakes-db and every count downstream are built from.
   */
  private deriveRecord(sessionId: string, text: string, askedBefore: string[]): void {
    try {
      const parsed = parseFeedback(text);
      if (!parsed) return;
      const answer = (this.lastAnswer.get(sessionId) ?? "").trim();
      if (!answer) return;
      const corrections = parsed.corrections
        // Unrecognized label → the default category, mirroring
        // DEFAULT_ERROR_CATEGORY in hooks/db_schema.py ("calculation": a slip
        // is the most common unknown in math practice).
        .map((c) => ({ ...c, category: normalizeCategory(c.category) ?? "calculation" }))
        .filter((c) => c.wrong && c.right);
      // The exercise THIS answer was for — captured by the caller before
      // `this.lastAsked` was overwritten with whatever this same reply asks
      // next. Reading `this.lastAsked` here directly would get the wrong one.
      const asked = askedBefore;
      // The item this answer was for is the one the server handed out for the
      // exercise that was on screen — not a guess made afterwards from the
      // text. Still checked against the queue before it is written: an id that
      // is not there would advance the wrong schedule, silently.
      const item = this.gradingItem.get(sessionId);
      const known = item ? this.itemExists(item.id) : false;
      const quality = Math.max(0, Math.min(5, Math.floor(parsed.score / 2)));
      const record = {
        record_id: `${sessionId}:derived:${Date.now()}`,
        session_id: sessionId,
        ts: Date.now(),
        // Math skill keys (C7): the active command names the practice; a
        // heading in the feedback is the fallback; computation the default.
        skill: COMMAND_SKILL[this.currentCommand.get(sessionId) ?? ""] ?? parsed.skill ?? "computation",
        exercise: (asked[0] ?? parsed.correctVersion ?? "").slice(0, 200),
        learner_answer: answer.slice(0, 500),
        score: Math.round(parsed.score),
        corrections,
        ...(item && known ? { item_id: item.id, sm2_quality: quality } : {}),
        ...(this.recordCompetence(sessionId) ? { competency: this.recordCompetence(sessionId) } : {}),
        derived: true,
      };
      const dir = path.join(this.dataDir(), ".records");
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(path.join(dir, `${sessionId}.jsonl`), JSON.stringify(record) + "\n", "utf8");
      console.log(
        `[Fluent] ✍ session ${sessionId}: record derived from the tutor's text ` +
          `(${record.score}/10, ${corrections.length} correction(s)) — the tool was not called`
      );
    } catch {
      /* best-effort: never cost the learner their answer */
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
  /**
   * The lesson as the tutor has to see it WHILE an answer is in front of it.
   *
   * The plan is credited after the reply, so when answer k arrives the plan says
   * k-1 done. The note then told the tutor "1 exercise still to go, do not
   * close" at the sixth answer of six: it obeyed, skipped the feedback and asked
   * a seventh exercise. Measured, six runs of six: the last answer of every
   * lesson got no feedback and the lesson never closed. The answer in front is
   * going to be credited in this very turn, so it counts here — for the note,
   * for the guards, and for the "Review k/6" header.
   *
   * Not for a retry of an exercise already credited (it is not credited twice),
   * and not for a button.
   */
  lessonWithAnswerInFront(sessionId: string): LessonView & { drills: number } {
    const answered = (this.lastAsked.get(sessionId) ?? [])[0];
    return withAnswerInFront(this.lessonState(), {
      inLesson: this.currentCommand.get(sessionId) === "math-review",
      isAnswer:
        this.answerInFront.get(sessionId) === true &&
        (this.lastAnswer.get(sessionId) ?? "").trim() !== "",
      alreadyCredited: Boolean(answered && (this.lessonPlan().credited ?? []).includes(answered)),
    });
  }

  lessonState(): LessonView & { drills: number } {
    const plan = this.lessonPlan();
    const date = todayISO();
    let due = 0;
    try {
      const sr = JSON.parse(fs.readFileSync(path.join(this.dataDir(), "spaced-repetition.json"), "utf8"));
      due = lessonTarget(sr, date).due;
    } catch {
      /* queue unreadable: the plan's total still stands */
    }
    let material = 0;
    try {
      material = drillMaterial(
        JSON.parse(fs.readFileSync(path.join(this.dataDir(), "mistakes-db.json"), "utf8"))
      );
    } catch {
      /* no mistakes-db yet: treat as no material, which is the truth */
    }
    let level: string | undefined;
    try {
      const prof = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "learner-profile.json"), "utf8")
      );
      const raw = prof?.learner?.current_level;
      if (typeof raw === "string" && raw.trim()) level = raw.trim().toUpperCase();
    } catch {
      /* level is a nicety */
    }
    return {
      total: plan.total,
      done: Math.min(plan.done, plan.total),
      pending: Math.max(0, plan.total - plan.done),
      due,
      drills: Math.max(0, plan.total - due),
      slot: plan.slot_done ? null : plan.slot,
      material,
      level,
    };
  }

  /** The learner's math level (m1..m6) from the profile, upper-cased, or undefined. */
  private learnerLevel(): string | undefined {
    try {
      const prof = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "learner-profile.json"), "utf8")
      );
      const raw = prof?.learner?.current_level;
      return typeof raw === "string" && raw.trim() ? raw.trim().toUpperCase() : undefined;
    } catch {
      return undefined;
    }
  }

  /** WP5.2 — the profile's domain: explicit `domain` field first, level scale
   *  second (A1..C2 → language, m1..m7 → math), manifest default last. The
   *  Python twin is hooks/domain.py; config/domain.json is the manifest. */
  private domainForSession(): string {
    try {
      const prof = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "learner-profile.json"), "utf8")
      );
      const explicit = String(prof?.domain ?? "").trim().toLowerCase();
      if (explicit) return explicit;
      const lv = String(prof?.learner?.current_level ?? prof?.learner?.target_level ?? "").trim().toUpperCase();
      if (/^m\d/.test(lv)) return "math";
      if (/^[A-C][12]$/.test(lv)) return "language";
    } catch {
      /* fall through to the default below */
    }
    return "math";
  }

  /** The learner's native/target languages from the profile (language domain). */
  private learnerLanguages(): { native?: string; target?: string } {
    try {
      const prof = JSON.parse(
        fs.readFileSync(path.join(this.dataDir(), "learner-profile.json"), "utf8")
      );
      const pick = (v: unknown) =>
        typeof v === "string" && v.trim() && !v.includes("{") ? v.trim() : undefined;
      return { native: pick(prof?.learner?.native_language), target: pick(prof?.learner?.target_language) };
    } catch {
      return {};
    }
  }

  /** Where the learner is in this session — the UI shows it, deterministically. */
  sessionProgress(sessionId: string): {
    graded: number;
    goal: number;
    face: string;
    session: number;
    skill?: string;
    lesson: ReturnType<Agent["lessonState"]>;
    reasoning: ReturnType<typeof skillBadge>;
    problems: ReturnType<typeof skillBadge>;
    facts: ReturnType<typeof skillBadge>;
    mode: string | null;
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
    const daily = readDaily(dir);
    const graded = daily.graded;
    return {
      graded,
      goal,
      face: dailyFace(graded, goal),
      session: count,
      skill: lastSkill,
      lesson: this.lessonState(),
      reasoning: skillBadge(daily.reasoning),
      problems: skillBadge(daily.problems),
      facts: skillBadge(daily.facts),
      // The button ring (TRACKED_MODE_CMDS in web/app.js) is a purely
      // client-side variable, set only when the learner clicks a mode button —
      // it has no way to know the server is already in a mode after a page
      // reload or a resumed session (2026-09-22, Albert: "he perdut el
      // remarcat del botó Go" after nothing but a reload). Ship the server's
      // own idea of the mode so the client can sync the ring to it instead of
      // guessing from local clicks alone.
      mode: this.currentCommand.get(sessionId) ?? null,
    };
  }

  /** The wrap-up note for this turn, or null. Given once per session. */
  /**
   * The teacher's topics (`topics.txt`, or `topics.md`, in the profile), as a
   * note — or null when there is no file, it is empty, or it cannot be read.
   * Read every turn: editing the file takes effect on the next message, no
   * restart. The rotation follows the day and the answers so far, so every
   * topic gets its turn instead of the first two being repeated.
   */
  private topicsNoteFor(sessionId: string): string | null {
    try {
      for (const name of ["topics.txt", "topics.md"]) {
        const f = path.join(this.dataDir(), name);
        if (!fs.existsSync(f)) continue;
        const topics = parseTopics(fs.readFileSync(f, "utf8"));
        if (topics.length === 0) return null;
        const day = Math.floor(Date.parse(todayISO()) / 86_400_000) || 0;
        const seed = day + this.gradedSoFar(sessionId).count;
        return topicsNote(topics, seed, this.learnerLevel());
      }
    } catch {
      /* a topics file that cannot be read must never cost the learner a turn */
    }
    return null;
  }

  /**
   * The competence the next free-practice exercise is about (Phase 2 of
   * docs/ESQUEMA-APRENENTATGE.md), as a note — or null when the profile has no
   * curriculum. The choice is Python's (hooks/curriculum.py next); the server
   * only asks, hands it over, and checks afterwards that the exercise is about
   * it. Same pattern as the Lesson's item: the answer arriving now belongs to the
   * PREVIOUS assignment, so it moves to `grading` before a new one is made.
   */

  private curriculumNoteFor(sessionId: string): string | null {
    const prev = this.assignedCompetence.get(sessionId);
    const answering = this.answerInFront.get(sessionId) === true;
    if (prev && answering) this.gradingCompetence.set(sessionId, prev);
    else this.gradingCompetence.delete(sessionId);
    this.assignedCompetence.delete(sessionId);
    try {
      const args = [
        "python3", path.join(this.root, "hooks", "curriculum.py"), "next", "--auto",
        // The LOCAL day: the path takes its days from the records' timestamps that way.
        "--data", this.dataDir(), "--today", new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
      ];
      // Only an exercise that was really put on screen counts as "the one just asked"
      // (a greeting or a menu is not).
      if (prev && answering && prev.shown) args.push("--last", prev.id);
      // Vocabulary asks one word at a time: only competences that have words.
      if (this.currentCommand.get(sessionId) === "math-vocab") args.push("--vocab");
      // Measured 2026-09-22: this failed silently mid-session (exit code
      // swallowed, no log) and the tutor was left with NO curriculum note at
      // all for several turns in a row — no instruction of what to ask next,
      // so it just kept repeating the exercise shape already sitting in its
      // context. A `.records` file being written by the server at the exact
      // moment Python reads it is the likely cause (a partial JSON line), and
      // that is a one-turn race, not a real failure — so retry once before
      // giving up, and always log what actually went wrong so a repeat is
      // diagnosable instead of invisible.
      const spawn = () =>
        Bun.spawnSync(args, {
          cwd: this.root,
          env: { ...process.env, FLOWED_DATA_DIR: this.dataDir(), FLOWED_ROOT: this.root },
          stdout: "pipe",
          stderr: "pipe",
        });
      let r = spawn();
      if (r.exitCode !== 0) {
        console.log(
          `[Fluent] ⚠ session ${sessionId}: curriculum.py next failed (exit ${r.exitCode}), retrying once — ` +
            `${r.stderr.toString().trim().slice(0, 300)}`
        );
        r = spawn();
      }
      if (r.exitCode !== 0) {
        console.log(
          `[Fluent] ✗ session ${sessionId}: curriculum.py next failed twice, no curriculum note this turn — ` +
            `${r.stderr.toString().trim().slice(0, 300)}`
        );
        return null;
      }
      const j = JSON.parse(r.stdout.toString() || "{}") as {
        id?: string; name?: string; can_do?: string; signals?: string[]; words?: string[]; vocab?: boolean;
        kind?: string; note?: string;
      };
      if (!j.id || !j.note) return null;
      this.assignedCompetence.set(sessionId, {
        id: j.id, name: String(j.name ?? j.id), can_do: j.can_do,
        signals: Array.isArray(j.signals) ? j.signals : [], vocab: Boolean(j.vocab), kind: j.kind,
        words: Array.isArray(j.words) ? j.words : [],
      });
      if (this.assignedCompetence.size > 500) this.assignedCompetence.clear();
      return j.note;
    } catch (e) {
      /* a curriculum that cannot be read must never cost the learner a turn */
      console.log(`[Fluent] ✗ session ${sessionId}: curriculum.py next threw — ${String(e).slice(0, 300)}`);
      return null;
    }
  }

  /** The competence to write on the record being made: only when the exercise it
   *  answers was seen to be about it, and not for vocabulary (Python resolves
   *  those from the word). */
  private recordCompetence(sessionId: string): string | null {
    const c = this.gradingCompetence.get(sessionId);
    return c && c.followed && !c.vocab ? c.id : null;
  }

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

    if (this.currentCommand.get(sessionId) !== "math-review") {
      // Outside the Lesson nothing is handed out, so nothing is being graded
      // against the queue.
      this.gradingItem.delete(sessionId);
      this.assignedItem.delete(sessionId);
    }
    // The curriculum hands out competences in free practice only.
    const cmdNow = this.currentCommand.get(sessionId) ?? "";
    const compNote =
      cmdNow === "math-learn" || cmdNow === "math-vocab" ? this.curriculumNoteFor(sessionId) : null;
    if (cmdNow !== "math-learn" && cmdNow !== "math-vocab") {
      this.gradingCompetence.delete(sessionId);
      this.assignedCompetence.delete(sessionId);
    }

    if (this.currentCommand.get(sessionId) === "math-review") {
      const lesson = this.lessonWithAnswerInFront(sessionId);
      if (lesson.pending > 0) {
        // STATE, not a script — see lessonNote() in pacing.ts for what that
        // distinction cost on 2026-09-16 and why it is not negotiable.
        // The item for the NEXT exercise. What is on screen right now was the
        // previous assignment, and that is what the answer arriving this turn
        // will be about — so it moves aside before a new one is made.
        const prev = this.assignedItem.get(sessionId);
        // Set it or clear it — never leave the last one standing. A stale
        // assignment outlives its lesson, and the record tool now trusts this
        // map: one forgotten delete and a Vocabulary answer advances a review
        // item nobody asked about.
        if (prev) this.gradingItem.set(sessionId, prev);
        else this.gradingItem.delete(sessionId);
        let assigned: AssignedItem | null = null;
        try {
          const sr = JSON.parse(
            fs.readFileSync(path.join(this.dataDir(), "spaced-repetition.json"), "utf8")
          );
          assigned = nextDueItem(sr, todayISO(), this.usedItems.get(sessionId) ?? []);
        } catch {
          /* no queue: the lesson runs on weak patterns, as before */
        }
        if (assigned) {
          this.assignedItem.set(sessionId, assigned);
          const used = this.usedItems.get(sessionId) ?? [];
          if (!used.includes(assigned.id)) used.push(assigned.id);
          this.usedItems.set(sessionId, used.slice(-60));
        } else {
          this.assignedItem.delete(sessionId);
        }
        const base = lessonNote(
          lesson, this.lessonPlan().covered, this.lastAsked.get(sessionId)?.[0], assigned
        );
        // Only where the tutor is choosing the subject itself: an assigned review
        // item always wins over a topic. (With the bank on, Review never gets
        // here — tryBankReviewTurn serves it; this is the model fallback.)
        const topics = !assigned ? this.topicsNoteFor(sessionId) : null;
        return topics ? `${base} ${topics}` : base;
      }

      // The last answer of the lesson is graded in this very turn, so the item
      // that was on screen still has to reach its record — the lesson being
      // over does not mean the review did not happen.
      const last = this.assignedItem.get(sessionId);
      // Set it or clear it: a message after the lesson is over answers nothing.
      if (last) this.gradingItem.set(sessionId, last);
      else this.gradingItem.delete(sessionId);
      this.assignedItem.delete(sessionId);

      // The lesson is FINISHED. Without this the tutor received no instruction
      // at all once the count ran out and simply carried on — exercise 7, 8,
      // 9 — asking the same shape of question for ever. A lesson that does not
      // end is not a lesson, and for an eight-year-old it is just boredom.
      return (
        `Today's lesson is COMPLETE: all ${lesson.total} exercises are done. ` +
        `Do NOT present another exercise. Finish evaluating the answer in front of you, then close: ` +
        `one warm line saying the lesson is done, a two-line summary (what went well, what to work on), ` +
        `and invite them to pick any practice they like with the buttons at the top — or to stop for today. ` +
        `If this lesson reviewed queue items, end with the math:review_results block. ` +
        `If they answer again anyway, respond briefly and point at the buttons; do not start a new exercise. ` +
        `Say nothing about this instruction itself.`
      );
    }

    // Outside the Lesson there is no pacing to impose — but the one thing the
    // tutor cannot know is what it has already asked today, and without it
    // Vocabulary repeated a word between visits in every measured run.
    const free = practiceNote(
      this.lessonPlan().covered,
      this.lastAsked.get(sessionId)?.[0],
      this.answerInFront.get(sessionId) === true
    );
    const cmd = this.currentCommand.get(sessionId) ?? "";
    const topics = [
      "math-learn", "math-vocab", "math-writing", "math-speaking", "math-reading",
    ].includes(cmd)
      ? this.topicsNoteFor(sessionId)
      : null;
    // WP5.2: language-domain pacing notes (domain-language.ts) — the writing
    // length table and the due-words note, only for a language profile.
    if (this.domainForSession() === "language") {
      if (cmd === "fluent-writing") {
        const w = writingLengthNote(this.learnerLevel());
        return [free, w, topics].filter(Boolean).join(" ") || null;
      }
      if (cmd === "fluent-vocab") {
        try {
          const sr = JSON.parse(fs.readFileSync(path.join(this.dataDir(), "spaced-repetition.json"), "utf8"));
          const due = vocabularyDueNote(sr, todayISO(), this.lessonPlan().covered, 5, this.learnerLanguages());
          if (due) return [free, due].filter(Boolean).join(" ") || null;
        } catch {
          /* no queue — fall through to the generic note */
        }
      }
    }
    if (this.currentCommand.get(sessionId) === "math-writing") {
      // No forced structure any more (Albert, 2026-09-24): Writing used to
      // borrow the exact grammar competence Go was drilling THIS turn
      // (writingFrameFor -> curriculum.py's writing_frame), so the two felt
      // like the same exercise back to back. Now that Go has a full,
      // reliable bank per competence (PLA-EXERCICIS-TANCATS.md, fase 2),
      // that reinforcement is no longer needed -- Writing is free (topic
      // from her own life, per math-writing's own SKILL.md) unless a
      // teacher's topic (topics.txt) sets one explicitly.
      // WP1.9: the old `writingLengthNote` (an A1..C2 table of email/postcard
      // tasks) is gone — it returned null for every m-level, and the task
      // length is the math-writing skill's own m1-m3 / upper-level table.
      return [free, topics].filter(Boolean).join(" ") || null;
    }
    return [free, compNote ?? topics].filter(Boolean).join(" ") || null;
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
          // Which practice the turn belonged to: without it the prompt size of
          // Writing / Speaking / Reading could not be told apart from the rest.
          command: this.currentCommand.get(sessionId) ?? null,
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
      const env = { ...process.env, FLOWED_DATA_DIR: this.dataDir(), FLOWED_PROJECT_DIR: root, FLOWED_ROOT: root };
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

      // Learner path (docs/ESQUEMA-APRENENTATGE.md, phase 0): tag the recorded
      // answers with the competences of this profile's curriculum. Derived from
      // the records and idempotent; it does nothing when the profile has no
      // curriculum, and it never blocks or breaks the persistence above.
      try {
        const cp = Bun.spawn(
          ["python3", path.join(root, "hooks", "curriculum.py"), "rebuild", "--auto", "--quiet", "--data", this.dataDir()],
          { cwd: root, env, stdout: "pipe", stderr: "pipe" }
        );
        await cp.exited;
      } catch {
        /* best-effort */
      }

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
      const env = { ...process.env, FLOWED_DATA_DIR: dataDir, FLOWED_PROJECT_DIR: root, FLOWED_ROOT: root };
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
