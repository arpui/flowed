// Fluent server — tools exposed to the LLM.
// Mirrors the opencode plugin toolbox for the learner agent:
//   - skill: load a math-* skill's SKILL.md (read-only)
//   - bash: run a shell command, filtered by the learner.md permission list
//   - math_deep_evaluate: delegate evaluation to the deep model role
//
// Each tool returns a plain string that is fed back to the model as the
// role:"tool" result AND persisted as a tool part.

import fs from "node:fs";
import path from "node:path";
import type { ToolDefinition, ToolContext } from "./llm";

export type { ToolContext };

export interface FluentPaths {
  root: string; // project root (fluent_dev/...)
  dataDir: string; // active learner data dir (~/.flowed/<id>/ or repo data/)
}

// ---- permission filter (learner.md `permission.bash`) ----------------------

const BASH_ALLOW: Array<{ re: RegExp; deny?: RegExp }> = [
  { re: /^python3 hooks\/read-db\.py/ },
  { re: /^python3 hooks\/update-db\.py/ },
  { re: /^python3 scripts\/list-profiles\.py/ },
  { re: /^cat \.flowed-active/ },
  { re: /^rm -f \.flowed-active/ },
];

function bashAllowed(command: string): boolean {
  const cmd = command.trim();
  return BASH_ALLOW.some(({ re }) => re.test(cmd));
}

// ---- deep-evaluation tool (port of plugin's math_deep_evaluate) ----------

// Canonical error categories (math taxonomy, DISSENY-MATEMATIQUES §4.4).
// SINGLE SOURCE: ERROR_CATEGORIES in hooks/db_schema.py —
// tests/test_error_categories.py fails if these two lists drift apart, and
// also checks the alias map below matches ERROR_CATEGORY_ALIASES there. Used
// by the deep rubric AND by math_record_answer's validation, so a category the
// parser would silently turn into the default ("calculation") is rejected at
// the moment it is written instead. The language-era categories live only in
// LEGACY_ERROR_CATEGORIES (Python side, for stored data and curriculum tags):
// the tutor must never emit them, so they are deliberately NOT accepted here.
export const ERROR_CATEGORIES = [
  "calculation",
  "sign",
  "place_value",
  "carrying",
  "order_of_operations",
  "wrong_operation",
  "procedure",
  "facts",
  "simplification",
  "unit",
  "misread",
  "incomplete",
] as const;

const CATEGORY_SET = new Set<string>(ERROR_CATEGORIES);

export function normalizeCategory(raw: unknown): string | null {
  const c = String(raw ?? "").trim().toLowerCase().replace(/[-\s]+/g, "_");
  // Surface terms in Catalan, Spanish and English; mirrors
  // ERROR_CATEGORY_ALIASES in hooks/db_schema.py (kept in sync by
  // tests/test_error_categories.py). Accents survive the normalization, so
  // accented spellings are listed as written.
  const aliases: Record<string, string> = {
    "calculo": "calculation",
    "cálculo": "calculation",
    "càlcul": "calculation",
    "compta": "calculation",
    "comptar": "calculation",
    "calcular": "calculation",
    "arithmetic": "calculation",
    "aritmética": "calculation",
    "aritmètica": "calculation",
    "signe": "sign",
    "signo": "sign",
    "minus": "sign",
    "plus": "sign",
    "negatiu": "sign",
    "positiu": "sign",
    "valor_posicional": "place_value",
    "posicio": "place_value",
    "posició": "place_value",
    "posicion": "place_value",
    "unitats_desenes_centenes": "place_value",
    "ones_tens_hundreds": "place_value",
    "carry": "carrying",
    "carries": "carrying",
    "carried": "carrying",
    "carry_over": "carrying",
    "transport": "carrying",
    "transportar": "carrying",
    "arrestando": "carrying",
    "arrestament": "carrying",
    "llevadas": "carrying",
    "ordre": "order_of_operations",
    "orden": "order_of_operations",
    "ordre_d'operacions": "order_of_operations",
    "orden_de_operaciones": "order_of_operations",
    "orden_operaciones": "order_of_operations",
    "operation_order": "order_of_operations",
    "operator_precedence": "order_of_operations",
    "precedence": "order_of_operations",
    "bodmas": "order_of_operations",
    "pemdas": "order_of_operations",
    "operacio_equivocada": "wrong_operation",
    "operació_equivocada": "wrong_operation",
    "operacion_equivocada": "wrong_operation",
    "operación_equivocada": "wrong_operation",
    "wrong_op": "wrong_operation",
    "operation_choice": "wrong_operation",
    "procediment": "procedure",
    "procedimiento": "procedure",
    "sequencia": "procedure",
    "seqüència": "procedure",
    "method": "procedure",
    "mètode": "procedure",
    "fet_basic": "facts",
    "fet_bàsic": "facts",
    "basic_fact": "facts",
    "hecho_basico": "facts",
    "hecho_básico": "facts",
    "taula": "facts",
    "taules": "facts",
    "tabla": "facts",
    "tablas": "facts",
    "times_table": "facts",
    "times_tables": "facts",
    "multiplicar": "facts",
    "memorization": "facts",
    "simplificacio": "simplification",
    "simplificació": "simplification",
    "simplificación": "simplification",
    "simplify": "simplification",
    "simplified": "simplification",
    "unsimplified": "simplification",
    "not_simplified": "simplification",
    "lowest_terms": "simplification",
    "unitat": "unit",
    "units": "unit",
    "unidad": "unit",
    "unidades": "unit",
    "measurement": "unit",
    "lectura": "misread",
    "enunciat": "misread",
    "enunciado": "misread",
    "reading": "misread",
    "misreading": "misread",
    "comprehension": "misread",
    "problem_statement": "misread",
    "incomplet": "incomplete",
    "incompleto": "incomplete",
    "partial": "incomplete",
    "unfinished": "incomplete",
    "half_done": "incomplete",
  };
  const canon = aliases[c] ?? c;
  return CATEGORY_SET.has(canon) ? canon : null;
}

// WP3.1 (C3): the MATH rubric. It replaces the language rubric that judged
// "communicativeness" and corrected words: here the deliverable is a line of
// work, and what is judged is the answer, the PROCEDURE, the justification and
// the communication of the math — never the Catalan of the explanation (a
// language slip in the learner's own language is not a math error; the
// feedback-formatter skill says the same, and the categories below are the
// math taxonomy, not grammar names).
//
// Score bands are deliberately the SAME scale the closed path uses — the steps
// v1/v2 grader (hooks/bank.py `finalize_steps`) hands out 10 (everything right
// first try) / 7 (a step needed a retry) / 3 (a step had to be revealed), and
// an open rubric that scored by a different logic would make the reasoning
// counters and the bank counters incomparable. Mapping:
//   10   = result right (when the task has one), procedure sound AND complete,
//          justification present — the closed 10.
//   8-9  = everything sound; only minor communication slips (units, notation,
//          an unsimplified form) — still the closed 10 band.
//   5-7  = the core procedure is right but something a second attempt would
//          fix: missing justification, one calculation slip inside an
//          otherwise sound procedure — the closed 7 ("va necessitar un segon
//          intent").
//   0-4  = the procedure or the result is wrong, the task was misread, or the
//          learner gave only a bare answer with no reasoning at all — the
//          closed 3 ("no et sortia; te'l vaig haver de revelar").
export const DEEP_RUBRIC = [
  "You are the evaluation engine of the FlowMath math-tutoring system (the 'deep' model role).",
  "You receive ONE learner answer to an open math task plus its context. Judge the MATH and the",
  "reasoning — never the language the answer is written in: a spelling or grammar slip in the",
  "learner's own language is not an error here. Produce a structured evaluation with exactly these sections:",
  "",
  "## CORRECTIONS",
  // Categories: keep in sync with ERROR_CATEGORIES in hooks/db_schema.py
  // (tests/test_error_categories.py fails if they drift apart).
  'One line per error, in EXACTLY this shape: `- "incorrect" → **"correct"** (category — short reason)`.',
  `Allowed categories: ${ERROR_CATEGORIES.join(", ")}.`,
  "Quote numbers, operations or whole lines of work — never words of the learner's language.",
  "Prefix each line with its severity: 🔴 critical | 🟡 moderate | 🟢 minor. If there are no errors, write: None.",
  "",
  "## CORRECT VERSION",
  "The full corrected answer (identical to the learner's answer if there are no errors).",
  "",
  "## SCORE",
  "An integer 0-10 plus one justification line. Judge four dimensions:",
  "- answer: is the final result correct, when the task has one",
  "- procedure: are the steps sound and complete — the operations, their order, the carrying",
  "- justification: does the learner say WHY, not just WHAT; a bare result with no reasoning is weak here",
  "- communication: is the math written clearly — notation, units, one operation per line",
  "Bands — the same 10/7/3 scale the closed exercises use (10 all-first-try / 7 needed a retry / 3 needed revealing):",
  "10 = result right (when present), procedure sound and complete, justification present, nothing to fix;",
  "8-9 = everything sound, only minor communication slips (units, notation, an unsimplified form);",
  "5-7 = the core procedure is right but something a second attempt would fix — missing justification,",
  "one calculation slip inside an otherwise sound procedure;",
  "0-4 = the procedure or the result is wrong, the task was misread, or the learner gave only a bare",
  "answer with no reasoning at all.",
  "Band anchors — before scoring, match the answer against these three (same learner, same scale):",
  "  ANCHOR 3 — bare answer, right number, no work: task «escriu les operacions (una per línia) i",
  "  el resultat», answer «El resultat és 20.» → SCORE: 3. The number may be right, but procedure",
  "  and justification are empty: a bare answer NEVER scores above 4, whatever the result.",
  "  ANCHOR 6 — sound procedure, one slip: «12 + 7 = 29. Per què funciona: perquè descompondre no",
  "  canvia el resultat.» → SCORE: 6. The idea is right and shown; one slip a second attempt fixes.",
  "  ANCHOR 9 — complete work with the reason: «42 ÷ 7 = 6. L'enunciat demana repartir entre iguals,",
  "  per això divisió.» → SCORE: 9. Operations shown, result right, the WHY present. A complete",
  "  correct answer scores 8-10 — do NOT hold it down to 5-7 for being short or plain.",
  "Points come from the WORK SHOWN (operations, steps, the stated reason), never from the final",
  "number alone: correct number with no work shown = 0-4; correct work shown with its reason = 8-10.",
  "",
  "## FEEDBACK",
  "1-2 encouraging sentences for the learner, naming what they got right.",
  "",
  "Rules: stay compact and factual; never address the learner directly (the tutor presents your output);",
  "never invent errors that are not in the answer; write the corrections in the learner's language named",
  "in the context, but grade only the math.",
].join("\n");

// ---- open-task kinds (WP3.1) ------------------------------------------------
// The shapes of open math practice the tutor can send. WP3.3's Raonament
// (📝 math-writing) sends 'explain' / 'error-analysis' / 'compare-strategies';
// WP3.2's open word problems will send 'word-problem'. The rubric is one
// rubric — the kind only tells the evaluator what the learner was asked, so it
// judges the right deliverable (a justification vs a found error vs a chosen
// strategy).
export const DEEP_TASKS = ["explain", "error-analysis", "compare-strategies", "word-problem"] as const;

// Read-old/write-new (same pattern as FLUENT_*→FLOWED_* in scripts/lib-paths.sh):
// the language-era task names are what the prompts sent until WP3.1
// ('writing' | 'speaking' | 'reading' | 'scoring'). A stale prompt or a chatty
// model may still send one — map it to its math kind instead of rejecting the
// call and losing the evaluation.
const LEGACY_DEEP_TASKS: Record<string, string> = {
  writing: "explain",
  speaking: "explain",
  reading: "word-problem",
  scoring: "explain",
  // other spellings a model drifts into
  "explain-reasoning": "explain",
  reasoning: "explain",
  "word-problem-solution": "word-problem",
  "strategy-comparison": "compare-strategies",
  "error-correction": "error-analysis",
  "find-error": "error-analysis",
};

export function normalizeDeepTask(raw: unknown): string {
  const t = String(raw ?? "").trim().toLowerCase().replace(/[\s_]+/g, "-");
  if ((DEEP_TASKS as readonly string[]).includes(t)) return t;
  return LEGACY_DEEP_TASKS[t] ?? "explain";
}

// ---- skill keys (C7) ---------------------------------------------------------
// The five math practices; the record's `skill` field is persisted into
// .records/ and read back by persist-session/accumulate-session, so it must
// carry math keys. Read-old/write-new: records written before WP3.1 (and older
// prompts) carry the language-era names — normalizeSkillKey maps them, and
// hooks/db_schema.py normalize_skill_key mirrors it for the stored side.
export const SKILL_KEYS = ["computation", "steps", "problems", "reasoning", "facts"] as const;

const LEGACY_SKILL_KEYS: Record<string, string> = {
  writing: "reasoning",
  speaking: "reasoning",
  listening: "facts",
  reading: "problems",
  vocabulary: "facts",
  grammar: "computation",
};

// Surface names for the math practices (a feedback heading like
// "## Repte de Raonament", a chatty model's skill argument) — mirrors
// SKILL_SURFACE_ALIASES in hooks/db_schema.py.
const SKILL_SURFACE_ALIASES: Record<string, string> = {
  raonament: "reasoning",
  razonamiento: "reasoning",
  reasoning: "reasoning",
  problema: "problems",
  problemes: "problems",
  problemas: "problems",
  problem: "problems",
  passos: "steps",
  pasos: "steps",
  step: "steps",
  fet: "facts",
  fets: "facts",
  hecho: "facts",
  hechos: "facts",
  calcul: "computation",
  "càlcul": "computation",
  calculo: "computation",
  "cálculo": "computation",
};

export function normalizeSkillKey(raw: unknown): string {
  const s = String(raw ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if ((SKILL_KEYS as readonly string[]).includes(s)) return s;
  const legacy = LEGACY_SKILL_KEYS[s];
  if (legacy) return legacy;
  return SKILL_SURFACE_ALIASES[s] ?? "computation";
}

export interface DeepEvaluator {
  /** Config for the deep model role. */
  model: string;
  baseURL: string;
  temperature: number;
  maxTokens: number;
  timeoutMs: number;
}

const deepUnavailable = (detail: string) =>
  `DEEP UNAVAILABLE: ${detail}\nFallback: evaluate the answer yourself using the format CORRECTIONS / CORRECT VERSION / SCORE / FEEDBACK.`;

// ---- loop guards (same as the plugin) --------------------------------------

const PLACEHOLDER_RE =
  /^(placeholder|todo|tbd|tbc|fixme|n\/a|na|none|null|undefined|test(ing)?|example|exemple|ejemplo|dummy|sample|lorem|ipsum|answer|your answer|ignore|stop|final|done|ok|okay|\.{2,}|…+)$/i;
const isRealAnswer = (t: unknown) => {
  const s = String(t ?? "").trim();
  if (s.length < 3) return false;
  return !PLACEHOLDER_RE.test(s);
};

function makeRejectTracker(maxRejections: number) {
  // sessionID -> { count, seen:Set, disabled }
  const sessions = new Map<string, { count: number; seen: Set<string>; disabled: boolean }>();
  const norm = (t: unknown) => String(t ?? "").trim().toLowerCase();
  return {
    register(sid: string, answer: unknown): { repeated: boolean; disabled: boolean; count: number } {
      let s = sessions.get(sid);
      if (!s) {
        s = { count: 0, seen: new Set(), disabled: false };
        sessions.set(sid, s);
        if (sessions.size > 200) sessions.clear();
      }
      s.count += 1;
      const key = norm(answer);
      const repeated = s.seen.has(key);
      s.seen.add(key);
      if (repeated || s.count >= maxRejections) s.disabled = true;
      return { repeated, disabled: s.disabled, count: s.count };
    },
    clear(sid: string) {
      const s = sessions.get(sid);
      if (s) {
        s.count = 0;
        s.seen.clear();
        s.disabled = false;
      }
    },
    isDisabled(sid: string) {
      return !!sessions.get(sid)?.disabled;
    },
  };
}

const DISABLED_MSG =
  "DEEP UNAVAILABLE: this tool is DISABLED for this session — it was already called repeatedly with non-answer content. STOP calling it now. Do not evaluate anything with it. Continue the session directly: present the next exercise to the learner and wait for their answer.";

// ---- tools -----------------------------------------------------------------

export function buildTools(opts: {
  root: string;
  dataDir: () => string;
  deep: DeepEvaluator;
  /** The queue item the SERVER put on screen for the exercise now being
   *  graded, per session. The tutor is never told the id — the note carries
   *  only the item's content — so asking it to copy one back was asking for a
   *  number it does not have, and every record came back without one. What the
   *  model must report, the server derives: same rule as the counter and the
   *  marker. Still validated against the queue below. */
  gradingItem?: (sessionId: string) => { id: string } | null;
  /** The curriculum competence the exercise being graded was built for (free
   *  practice), when the server verified it. Written on the record as `competency`. */
  gradingCompetence?: (sessionId: string) => string | null;
}): { definitions: ToolDefinition[]; deepCalls: Map<string, number> } {
  const rejects = makeRejectTracker(3);
  const deepCalls = new Map<string, number>(); // messageID -> count this turn

  const skillTool: ToolDefinition = {
    name: "skill",
    description:
      "Load a Fluent skill's instructions (a Markdown SKILL.md) into your context. Only 'math-*' skills are available. Returns the skill content to follow exactly.",
    parameters: {
      type: "object",
      properties: { name: { type: "string", description: "Skill name, e.g. 'math-learn'." } },
      required: ["name"],
    },
    execute: async (args: Record<string, unknown>) => {
      const name = String(args.name ?? "").trim();
      if (!/^(math|fluent)-[a-z0-9-]+$/.test(name)) {
        return `[skill error: '${name}' is not a valid domain skill name]`;
      }
      const file = path.join(opts.root, "skills", name, "SKILL.md");
      try {
        const content = fs.readFileSync(file, "utf8");
        return `<skill_content name="${name}">\n${content}\n</skill_content>`;
      } catch {
        return `[skill error: no SKILL.md found for '${name}' at ${file}]`;
      }
    },
  };

  const bashTool: ToolDefinition = {
    name: "bash",
    description:
      "Run a shell command and return its output. Only a small allow-list of Fluent maintenance commands is permitted (reading learner state, listing/switching profiles). Anything else is denied.",
    parameters: {
      type: "object",
      properties: { command: { type: "string", description: "The shell command to run." } },
      required: ["command"],
    },
    execute: async (args: Record<string, unknown>) => {
      const command = String(args.command ?? "").trim();
      if (!bashAllowed(command)) {
        return `[bash denied] command not in the allow-list (learner permission): ${command.slice(0, 200)}`;
      }
      const cwd = opts.root;
      const env = { ...process.env, FLOWED_DATA_DIR: opts.dataDir(), FLOWED_PROJECT_DIR: opts.root, FLOWED_ROOT: opts.root };
      try {
        const proc = Bun.spawn(["bash", "-c", command], { cwd, env, stdout: "pipe", stderr: "pipe" });
        const exit = await proc.exited;
        const out = await new Response(proc.stdout).text();
        const err = await new Response(proc.stderr).text();
        return err && exit !== 0 ? `[exit ${exit}]\n${out}\n${err}` : `${out}${err}`.trim();
      } catch (e) {
        return `[bash error: ${e instanceof Error ? e.message : String(e)}]`;
      }
    },
  };

  const deepTool: ToolDefinition = {
    name: "math_deep_evaluate",
    description:
      "Delegate evaluation of a learner answer to the deep model role (focused math rubric in a clean context: answer, procedure, justification, communication — never language). Use it for open math answers: a reasoning explanation, an error found and explained, a strategy comparison, or an open word-problem solution. Never for closed bank items — the server grades those itself. Call it at most ONCE, and only with the learner's real, already-submitted answer — never with placeholder, hypothetical or invented content. Returns a structured evaluation (CORRECTIONS / CORRECT VERSION / SCORE / FEEDBACK) to present to the learner in your feedback format. If the result starts with 'DEEP UNAVAILABLE', follow the instructions in the message (usually: evaluate the answer yourself in the same format, or continue the session without calling the tool).",
    parameters: {
      type: "object",
      properties: {
        task: { type: "string", description: `Open-task kind: ${DEEP_TASKS.map((t) => `'${t}'`).join(" | ")} (legacy names writing/speaking/reading/scoring are still accepted and mapped)` },
        answer: { type: "string", description: "The learner's exact answer to evaluate" },
        context: { type: "string", description: "Exercise context: the original task, the learner's language and level, and the expected procedure or key points" },
      },
      required: ["task", "answer", "context"],
    },
    execute: async (args: Record<string, unknown>, ctx?: ToolContext) => {
      const sid = ctx?.sessionID ?? "unknown";
      const mid = ctx?.messageID ?? "unknown";
      if (!isRealAnswer(args.answer)) {
        if (rejects.isDisabled(sid)) return DISABLED_MSG;
        const r = rejects.register(sid, args.answer);
        if (r.disabled) return DISABLED_MSG;
        return `DEEP UNAVAILABLE (rejection ${r.count} of 3): the 'answer' argument is empty or looks like placeholder content — there is no real learner answer to evaluate. Menu selections and navigation words (numbers, "ok", "next") are never answers. Do NOT call this tool with invented content; continue the session instead. One more rejected call disables this tool for the whole session.`;
      }
      const n = (deepCalls.get(mid) ?? 0) + 1;
      deepCalls.set(mid, n);
      if (deepCalls.size > 1000) deepCalls.clear();
      if (n > 1) {
        const r = rejects.register(sid, args.answer);
        if (r.disabled) return DISABLED_MSG;
        return `DEEP UNAVAILABLE (rejection ${r.count} of 3): this tool was already called for the current answer. Present the evaluation you already received — do not call it again this turn.`;
      }

      const task = normalizeDeepTask(args.task);
      const cfg = opts.deep;
      const url = `${cfg.baseURL.replace(/\/+$/, "")}/chat/completions`;
      const body = {
        model: cfg.model,
        temperature: cfg.temperature,
        max_tokens: cfg.maxTokens,
        stream: false,
        chat_template_kwargs: { enable_thinking: false },
        messages: [
          { role: "system", content: DEEP_RUBRIC },
          {
            role: "user",
            content: `Task: ${task}\n\nContext:\n${args.context}\n\nLearner answer:\n"""\n${args.answer}\n"""`,
          },
        ],
      };
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new Error(`timeout after ${cfg.timeoutMs} ms`)), cfg.timeoutMs);
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          return deepUnavailable(`HTTP ${res.status} from ${url}: ${t.slice(0, 300)}`);
        }
        const data = (await res.json()) as any;
        const text = data?.choices?.[0]?.message?.content;
        if (!text) return deepUnavailable(`empty response: ${JSON.stringify(data).slice(0, 300)}`);
        rejects.clear(sid);
        return text;
      } catch (e) {
        return deepUnavailable(String(e instanceof Error ? e.message : e));
      } finally {
        clearTimeout(timer);
      }
    },
  };

  // ---- math_record_answer: structured grading (P1-5) --------------------
  // The tutor DECLARES what it graded instead of only narrating it. The server
  // validates and appends the record; the Python layer prefers records over the
  // prose parsers and logs any divergence between the two.
  const MAX_RECORDS_PER_SESSION = 300;
  const recordCounts = new Map<string, number>();

  const queueItems = (dataDir: string): Set<string> => {
    try {
      const raw = fs.readFileSync(path.join(dataDir, "spaced-repetition.json"), "utf8");
      return new Set(Object.keys((JSON.parse(raw)?.items ?? {}) as Record<string, unknown>));
    } catch {
      return new Set();
    }
  };

  const recordTool: ToolDefinition = {
    name: "math_record_answer",
    description:
      "Record ONE graded answer in the learner's databases. Call it once per answer, right after you show the learner your feedback, with the same values you just showed them. This is what actually stores the result: your message text is for the learner, this call is the data. If it returns REJECTED, fix the arguments and call it again once.",
    parameters: {
      type: "object",
      properties: {
        skill: { type: "string", description: `${SKILL_KEYS.join(" | ")} — the math practice this answer belongs to (reasoning for explaining/justifying, problems for word problems, facts for the drill)` },
        exercise: { type: "string", description: "The exercise you presented, one line." },
        learner_answer: { type: "string", description: "The learner's answer, verbatim." },
        score: { type: "number", description: "The score you gave, 0-10." },
        corrections: {
          type: "array",
          description: "One entry per mistake you corrected. Empty if the answer was right.",
          items: {
            type: "object",
            properties: {
              wrong: { type: "string", description: "The learner's incorrect text." },
              right: { type: "string", description: "The correct form." },
              category: { type: "string", description: `One of: ${ERROR_CATEGORIES.join(", ")}` },
              severity: { type: "string", description: "critical | moderate | minor" },
            },
            required: ["wrong", "right", "category"],
          },
        },
        item_id: {
          type: "string",
          description:
            "Leave this out unless you were given an explicit item id: when the exercise came from the review queue the server attaches the right id itself.",
        },
        sm2_quality: {
          type: "number",
          description: "0-5 recall quality for item_id. Omit and it is derived as floor(score / 2).",
        },
      },
      required: ["skill", "exercise", "learner_answer", "score"],
    },
    execute: async (args: Record<string, unknown>, ctx?: ToolContext) => {
      const sid = ctx?.sessionID ?? "unknown";
      const dataDir = ctx?.dataDir ?? opts.dataDir();

      const n = (recordCounts.get(sid) ?? 0) + 1;
      if (n > MAX_RECORDS_PER_SESSION) {
        return "REJECTED: too many records for this session; stop calling this tool and continue the practice.";
      }

      const score = Number(args.score);
      if (!Number.isFinite(score) || score < 0 || score > 10) {
        return `REJECTED: score must be a number between 0 and 10 (got ${JSON.stringify(args.score)}).`;
      }
      const answer = String(args.learner_answer ?? "").trim();
      if (answer.length < 1) {
        return "REJECTED: learner_answer is empty — record the answer the learner actually sent.";
      }

      const corrections: Array<Record<string, string>> = [];
      const rawCorrections = Array.isArray(args.corrections) ? args.corrections : [];
      for (const raw of rawCorrections) {
        const c = (raw ?? {}) as Record<string, unknown>;
        const category = normalizeCategory(c.category);
        if (!category) {
          return `REJECTED: unknown category ${JSON.stringify(c.category)}. Allowed: ${ERROR_CATEGORIES.join(", ")}.`;
        }
        const wrong = String(c.wrong ?? "").trim();
        const right = String(c.right ?? "").trim();
        if (!wrong || !right) {
          return "REJECTED: every correction needs both `wrong` and `right`.";
        }
        const sev = String(c.severity ?? "moderate").trim().toLowerCase();
        corrections.push({
          wrong,
          right,
          category,
          severity: ["critical", "moderate", "minor"].includes(sev) ? sev : "moderate",
        });
      }

      let itemId = String(args.item_id ?? "").trim();
      let quality: number | null = null;
      let itemFromServer = false;
      if (!itemId) {
        const assigned = opts.gradingItem?.(sid) ?? null;
        if (assigned && queueItems(dataDir).has(assigned.id)) {
          itemId = assigned.id;
          itemFromServer = true;
        }
      }
      if (itemId) {
        if (!itemFromServer && !queueItems(dataDir).has(itemId)) {
          return `REJECTED: item_id "${itemId}" is not in this learner's review queue. Copy it verbatim from the due-items list, or omit item_id when the exercise did not come from the queue.`;
        }
        const q = args.sm2_quality === undefined ? Math.floor(score / 2) : Number(args.sm2_quality);
        if (!Number.isFinite(q) || q < 0 || q > 5) {
          return `REJECTED: sm2_quality must be 0-5 (got ${JSON.stringify(args.sm2_quality)}).`;
        }
        quality = Math.floor(q);
      }

      const record = {
        record_id: `${sid}:${ctx?.messageID ?? "m"}:${n}`,
        session_id: sid,
        ts: Date.now(),
        // Math skill keys (C7). Read-old/write-new: a language-era name still
        // arriving from an older prompt is mapped to its math counterpart
        // (writing→reasoning, reading→problems, vocabulary→facts, …) instead
        // of being stored verbatim and inventing a phantom skill downstream.
        skill: normalizeSkillKey(args.skill),
        exercise: String(args.exercise ?? "").trim(),
        learner_answer: answer,
        score: Math.round(score),
        corrections,
        ...(itemId ? { item_id: itemId, sm2_quality: quality } : {}),
        ...(opts.gradingCompetence?.(sid) ? { competency: opts.gradingCompetence(sid) } : {}),
      };

      try {
        const dir = path.join(dataDir, ".records");
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(path.join(dir, `${sid}.jsonl`), JSON.stringify(record) + "\n", "utf8");
      } catch (e) {
        return `REJECTED: could not store the record (${e instanceof Error ? e.message : String(e)}). Continue the session; do not retry more than once.`;
      }
      recordCounts.set(sid, n);
      if (recordCounts.size > 500) recordCounts.clear();

      const bits = [`score ${record.score}/10`, `${corrections.length} correction(s)`];
      if (itemId) bits.push(`review ${itemId} quality ${quality}`);
      return `recorded (${bits.join(", ")}). Continue the session — say nothing about this call.`;
    },
  };

  // ---- math_setup_profile: onboarding that can actually finish (S14) -----
  // /math-setup interviews the learner and then has to WRITE the profile.
  // In this runtime it had no way to: no write tool, and its python one-liners
  // are denied by the allow-list — so a profile created by new-user.sh stayed a
  // template for ever while the web kept auto-starting the interview. This tool
  // is that missing write, with the fields typed and validated.
  // Math level scale (DISSENY-MATEMATIQUES D3): m1..m6 the primary cycle,
  // m7 = 1r ESO (WP1.1); m8/m9 reserved for 2n/3r ESO.
  const M_LEVELS = ["m1", "m2", "m3", "m4", "m5", "m6", "m7"];

  const setupTool: ToolDefinition = {
    name: "math_setup_profile",
    description:
      "Write the learner's profile at the END of the /math-setup interview, once you have their answers. Call it ONCE. It fills learner-profile.json (name, languages, levels, daily minutes, goals) and marks the setup as complete, so the app stops asking. If it returns REJECTED, fix what it names and call it again once. Never call it during normal practice.",
    parameters: {
      type: "object",
      properties: {
        name: { type: "string", description: "The learner's first name, as they wrote it." },
        target_language: { type: "string", description: 'Subject being learned — always "Math".' },
        native_language: { type: "string", description: "The language the tutor explains in, in English (e.g. Catalan). Never guess: use what they said." },
        current_level: { type: "string", description: `Math level now: ${M_LEVELS.join(" | ")}` },
        target_level: { type: "string", description: `Math level wanted: ${M_LEVELS.join(" | ")}` },
        daily_minutes: { type: "number", description: "Minutes per day they committed to (5-240)." },
        goals: { type: "array", items: { type: "string" }, description: "Why they are practising, in their words (1-5 short items)." },
        motivation: { type: "string", description: "school | exam | practice | personal" },
        interests: { type: "array", items: { type: "string" }, description: "Up to 3 interests, used for warmer examples. Optional." },
        about: { type: "string", description: "One line about them, in their words. Optional." },
      },
      required: ["name", "target_language", "native_language", "current_level", "target_level"],
    },
    execute: async (args: Record<string, unknown>, ctx?: ToolContext) => {
      const dataDir = ctx?.dataDir ?? opts.dataDir();
      const profilePath = path.join(dataDir, "learner-profile.json");

      const name = String(args.name ?? "").trim();
      if (name.length < 1 || name.length > 60) {
        return "REJECTED: name must be the learner's first name, 1-60 characters.";
      }
      let target = String(args.target_language ?? "").trim();
      const native = String(args.native_language ?? "").trim();
      if (!target || !native) {
        return "REJECTED: target_language and native_language are both required.";
      }
      if (target.toLowerCase() === native.toLowerCase()) {
        return `REJECTED: target_language and native_language cannot both be "${target}". Ask the learner again which one they are learning.`;
      }
      if (target.toLowerCase() === "math") target = "Math"; // the one subject this fork teaches
      // m1..m6, stored lowercase ("M4" from a chatty model normalizes to "m4").
      const level = (v: unknown) => String(v ?? "").trim().toLowerCase();
      const current = level(args.current_level);
      const wanted = level(args.target_level);
      for (const [field, value] of [["current_level", current], ["target_level", wanted]] as const) {
        if (!M_LEVELS.includes(value)) {
          return `REJECTED: ${field} must be one of ${M_LEVELS.join(", ")} (got ${JSON.stringify(value)}). If the learner does not know, ask one placement question and decide yourself.`;
        }
      }
      let minutes = Number(args.daily_minutes);
      if (!Number.isFinite(minutes) || minutes <= 0) minutes = 30;
      minutes = Math.max(5, Math.min(240, Math.round(minutes)));

      let profile: Record<string, any>;
      try {
        profile = JSON.parse(fs.readFileSync(profilePath, "utf8"));
      } catch {
        return `REJECTED: no learner-profile.json in ${dataDir}. The profile directory must be created by the system owner (scripts/new-user.sh) before setup.`;
      }

      const today = new Date().toISOString().slice(0, 10);
      const learner = (profile.learner ??= {});
      learner.name = name;
      learner.target_language = target;
      learner.native_language = native;
      learner.current_level = current;
      learner.target_level = wanted;
      learner.daily_goal_minutes = minutes;
      if (typeof args.motivation === "string" && args.motivation.trim()) {
        learner.motivation = args.motivation.trim().toLowerCase();
      } else if (typeof learner.motivation !== "string" || /^\{.*\}$/.test(learner.motivation.trim())) {
        learner.motivation = "personal"; // template placeholder, never a real value
      }
      // Template placeholders like "{OTHER_LANGUAGES_YOU_SPEAK}" must not survive.
      if (Array.isArray(learner.other_languages)) {
        learner.other_languages = learner.other_languages.filter(
          (l: unknown) => typeof l === "string" && !/^\{.*\}$/.test(l.trim())
        );
      }
      if (typeof learner.learning_style === "string" && /^\{.*\}$/.test(learner.learning_style)) {
        learner.learning_style = "balanced";
      }
      const interests = (Array.isArray(args.interests) ? args.interests : [])
        .map((i) => String(i).trim())
        .filter(Boolean)
        .slice(0, 3);
      if (interests.length) learner.interests = interests;
      if (typeof args.about === "string" && args.about.trim()) {
        learner.about = args.about.trim().slice(0, 200);
      }

      const goals = (Array.isArray(args.goals) ? args.goals : [])
        .map((g) => String(g).trim())
        .filter(Boolean)
        .slice(0, 5);
      if (goals.length) profile.focus_areas = goals;

      profile.profile_created =
        typeof profile.profile_created === "string" && !/^\{.*\}$/.test(profile.profile_created)
          ? profile.profile_created
          : today;
      profile.last_updated = today;
      (profile.preferences ??= {}).setup_complete = true;
      if (Array.isArray(profile.achievements)) {
        for (const a of profile.achievements) {
          if (a && typeof a === "object" && /^\{.*\}$/.test(String(a.earned_date ?? ""))) {
            a.earned_date = today;
          }
        }
      }

      try {
        // Same backup convention the Python hooks use, then atomic replace.
        const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15);
        fs.copyFileSync(profilePath, `${profilePath}.backup-${stamp}`);
        const tmp = `${profilePath}.tmp`;
        fs.writeFileSync(tmp, JSON.stringify(profile, null, 2) + "\n", "utf8");
        fs.renameSync(tmp, profilePath);
      } catch (e) {
        return `REJECTED: could not write the profile (${e instanceof Error ? e.message : String(e)}).`;
      }

      return `profile saved: ${name} · ${native} → ${target} · ${current}→${wanted} · ${minutes} min/day. Setup is complete; the app will not ask again. Now show the learner their plan and invite them to start with a practice.`;
    },
  };

  return { definitions: [skillTool, bashTool, deepTool, recordTool, setupTool], deepCalls };
}
