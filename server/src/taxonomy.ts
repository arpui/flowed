// The taxonomy of a DOMAIN (WP6, 2026-10-08): the skills a practice is filed
// under, the error categories the tutor may emit, and their fallbacks.
//
// They belong to the domain of the profile, not to the core. Until now the
// core carried only the math ones, so a language learner's grammar slip became
// "calculation" and her vocabulary the math skill "facts" (found on test-lang:
// `calculation_I_went`, Càlcul/Fets in a language profile's Stats). The math
// tables stay in tools.ts (hooks/db_schema.py is their single source, kept in
// sync by tests/test_error_categories.py); the language ones live here and
// mirror hooks/db_schema.py LANGUAGE_* (tests/test_taxonomy.py keeps them so).
import fs from "node:fs";
import path from "node:path";

export const isLanguage = (domain?: string | null): boolean =>
  String(domain ?? "").trim().toLowerCase() === "language";

/** The profile's domain: explicit `domain` field, else the level scale
 *  (A1..C2 → language, m1..m7 → math), else math. Same rule as
 *  hooks/domain.py domain_for_profile. Never throws. */
export function domainOfDataDir(dataDir: string): string {
  try {
    const prof = JSON.parse(fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8"));
    const explicit = String(prof?.domain ?? "").trim().toLowerCase();
    if (explicit) return explicit;
    const lv = String(prof?.learner?.current_level ?? prof?.learner?.target_level ?? "").trim().toUpperCase();
    if (/^M\d/.test(lv)) return "math";
    if (/^[A-C][12]$/.test(lv)) return "language";
  } catch {
    /* no profile: the default below */
  }
  return "math";
}

// ---- language skills ---------------------------------------------------------
export const LANGUAGE_SKILL_KEYS = ["writing", "speaking", "vocabulary", "reading", "grammar", "listening"] as const;
export const DEFAULT_LANGUAGE_SKILL_KEY = "writing";

export const LANGUAGE_SKILL_ALIASES: Record<string, string> = {
  vocab: "vocabulary", vocabulari: "vocabulary", vocabulario: "vocabulary",
  words: "vocabulary", flashcards: "vocabulary", facts: "vocabulary",
  gramatica: "grammar", "gramàtica": "grammar", "gramática": "grammar",
  escriptura: "writing", escritura: "writing", redaccio: "writing",
  "redacció": "writing", spelling: "writing", ortografia: "writing",
  lectura: "reading", comprehension: "reading",
  parla: "speaking", oral: "speaking", conversa: "speaking",
  conversation: "speaking", pronunciation: "speaking",
  escolta: "listening", comprensio_oral: "listening",
  "comprensió_oral": "listening",
};

/** A math key arriving in a language profile lands on the nearest language
 *  skill instead of inventing a math skill there. */
export const MATH_TO_LANGUAGE_SKILL: Record<string, string> = {
  computation: "grammar", steps: "grammar", problems: "reading",
  reasoning: "writing", facts: "vocabulary",
};

export function normalizeLanguageSkill(raw: unknown): string {
  const s = String(raw ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if ((LANGUAGE_SKILL_KEYS as readonly string[]).includes(s)) return s;
  return LANGUAGE_SKILL_ALIASES[s] ?? MATH_TO_LANGUAGE_SKILL[s] ?? DEFAULT_LANGUAGE_SKILL_KEY;
}

/** Which practice (canonical command key) files under which language skill. */
export const LANGUAGE_COMMAND_SKILL: Record<string, string> = {
  "math-writing": "writing",
  "math-speaking": "speaking",
  "math-reading": "reading",
  "math-vocab": "vocabulary",
  "math-learn": "grammar",
};

/** Skills the Lesson watches for neglect, and the two it may reserve a slot for
 *  (FlowEd 0.5: "only the two that get quietly dropped"). */
export const LANGUAGE_TRACKED_SKILLS = ["writing", "reading", "speaking", "vocabulary"] as const;
export const LANGUAGE_SLOT_SKILLS = ["writing", "reading"] as const;

// ---- language error categories ------------------------------------------------
export const LANGUAGE_ERROR_CATEGORIES = [
  "grammar", "word_order", "tenses", "agreement", "articles",
  "prepositions", "pronouns", "vocabulary", "spelling", "punctuation",
  "capitalization", "formal_informal", "register", "missing", "comprehension",
] as const;
/** Ids of the oldest FlowEd: still accepted verbatim (stored data). */
export const LANGUAGE_OLD_CATEGORIES = ["writing", "pronunciation", "reflexive", "subject", "gerund"] as const;
export const DEFAULT_LANGUAGE_ERROR_CATEGORY = "grammar";

export const LANGUAGE_CATEGORY_ALIASES: Record<string, string> = {
  wordorder: "word_order",
  preposition: "prepositions",
  pronoun: "pronouns",
  tense: "tenses",
  informal_formal: "formal_informal",
  reading: "comprehension",
  inference: "comprehension",
  detail: "comprehension",
  past: "tenses",
  present: "tenses",
  future: "tenses",
  past_tense: "tenses",
  present_tense: "tenses",
  verb_tense: "tenses",
  verb: "tenses",
  conjugation: "tenses",
  article: "articles",
  capitalisation: "capitalization",
  caps: "capitalization",
  word_choice: "vocabulary",
  wording: "vocabulary",
  plural: "agreement",
  singular: "agreement",
  number: "agreement",
  subject_verb: "agreement",
  formality: "formal_informal",
  typo: "spelling",
};

/** The canonical language category, or null when the label is none (the record
 *  tool rejects it; the derived record falls back to the domain default). */
export function normalizeLanguageCategory(raw: unknown): string | null {
  const c0 = String(raw ?? "").trim().toLowerCase().replace(/[-\s]+/g, "_");
  const c = LANGUAGE_CATEGORY_ALIASES[c0] ?? c0;
  if ((LANGUAGE_ERROR_CATEGORIES as readonly string[]).includes(c)) return c;
  if ((LANGUAGE_OLD_CATEGORIES as readonly string[]).includes(c)) return c;
  return null;
}
