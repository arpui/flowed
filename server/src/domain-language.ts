// WP5.2 — the language-domain adapter. WP0.3 stripped this machinery from the
// core for the math product; in the unified core it lives HERE and agent.ts
// calls it only when the profile's domain is "language" (config/domain.json is
// the manifest; hooks/domain.py is the Python twin). Restored verbatim from
// flowed's pacing.ts — the language product's behavior, unchanged.
import { dueItemIds, normalizeExercise } from "./pacing";

export function writingLengthNote(level?: string | null): string | null {
  const l = String(level ?? "").trim().toUpperCase();
  const ask: Record<string, string> = {
    A1: "1-2 sentences of her own about one small topic from her life, with the one or two words she should use named in the task (\"Use: I have, It is\")",
    A2: "3-5 sentences of her own: a short note, a message or a postcard",
    B1: "50-70 words: an email with a greeting and a closing",
    B2: "80-120 words, with an argument to make",
    C1: "80-120 words, with an argument to make",
    C2: "80-120 words, with an argument to make",
  };
  const want = ask[l];
  if (!want) return null;
  const low = l === "A1" || l === "A2";
  return (
    `This learner's level is ${l}. Any writing exercise you set asks for ${want}` +
    (low
      ? ` — not an email or a letter, no long list of requirements, and never a gap to fill or a sentence ` +
        `to complete: that is Go's job. Here she writes her own words. One short task at a time: grade it, ` +
        `then set the next one in the same message`
      : ``) +
    `. Say nothing about this note.`
  );
}

export function vocabularyDueNote(
  sr: unknown,
  today: string,
  covered: readonly string[] = [],
  max = 5,
  langs: { native?: string; target?: string } = {}
): string | null {
  const items = (sr as { items?: Record<string, Record<string, unknown>> })?.items ?? {};
  const words: string[] = [];
  let rules = 0;
  for (const id of dueItemIds(sr, today)) {
    const it = items[id] ?? {};
    if (String(it.type ?? it.item_type ?? "") !== "vocabulary") {
      rules++;
      continue;
    }
    const content = String(it.content ?? "").trim();
    if (!content || covered.includes(normalizeExercise(content))) continue;
    if (words.length < max) {
      words.push(`"${content}"` + (it.answer ? ` (${String(it.answer)})` : ""));
    }
  }
  const bits: string[] = [];
  if (words.length) {
    bits.push(`Words due for review today — use these for your cards first: ${words.join(", ")}.`);
  }
  bits.push(
    `Every card is a noun, verb or adjective with its meaning — never an article ` +
      `("a", "an", "the"), a preposition ("on", "of", "in") or a piece of a grammar sentence.`
  );
  if (rules) {
    bits.push(
      `The review queue also holds grammar and spelling items: those are rules, not words — ` +
        `never turn one into a flashcard.`
    );
  }
  if (langs.native && langs.target) {
    bits.push(
      `A card shows a word in one language and asks for it in the other: a word written in ` +
        `${langs.native} asks "How do you say it in ${langs.target}?", a word written in ` +
        `${langs.target} asks "What does it mean in ${langs.native}?". Never ask for a word's ` +
        `meaning in the language it is already written in.`
    );
  }
  bits.push(`Say nothing about this note.`);
  return bits.join(" ");
}

export function languageDirectionGuard(text: string, target?: string, native?: string): string | null {
  if (!target || !native || target.trim().toLowerCase() === native.trim().toLowerCase()) return null;
  const m = /^#{1,6}\s*([^\n]*Speaking Practice[^\n]*)/im.exec(text);
  if (!m) return null;
  const heading = (m[1] ?? "").trim();
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const hasNative = new RegExp(`\\b${esc(native)}\\b`, "i").test(heading);
  const hasTarget = new RegExp(`\\b${esc(target)}\\b`, "i").test(heading);
  if (hasNative && !hasTarget) {
    return (
      `This Speaking session opened as "${heading}" — but the learner's target language is ` +
      `${target}, and ${native} is only their NATIVE language, never what Speaking practices. ` +
      `Write the turn again with the heading and every instruction about which language to ` +
      `speak correctly naming ${target}, not ${native}.`
    );
  }
  return null;
}

const SCRIPTS: Array<{ re: RegExp; langs: string[] }> = [
  { re: /[㐀-鿿豈-﫿]/u, langs: ["chinese", "japanese", "mandarin", "cantonese"] },
  { re: /[぀-ヿ]/u, langs: ["japanese"] },
  { re: /[가-힯ᄀ-ᇿ]/u, langs: ["korean"] },
  { re: /[Ѐ-ӿ]/u, langs: ["russian", "ukrainian", "bulgarian", "serbian", "belarusian", "macedonian"] },
  { re: /[Ͱ-Ͽ]/u, langs: ["greek"] },
  { re: /[؀-ۿ]/u, langs: ["arabic", "persian", "farsi", "urdu"] },
  { re: /[֐-׿]/u, langs: ["hebrew", "yiddish"] },
  { re: /[ऀ-ॿ]/u, langs: ["hindi", "marathi", "nepali"] },
  { re: /[฀-๿]/u, langs: ["thai"] },
];

/** Characters of a script that is neither the target nor the native language. */
export function foreignScript(text: string, target?: string, native?: string): RegExp | null {
  const mine = [target, native].map((l) => String(l ?? "").trim().toLowerCase());
  for (const s of SCRIPTS) {
    if (s.langs.some((l) => mine.includes(l))) continue;
    if (s.re.test(text)) return new RegExp(`${s.re.source}+`, "gu");
  }
  return null;
}

export function foreignScriptGuard(text: string, target?: string, native?: string): string | null {
  const re = foreignScript(text, target, native);
  if (!re) return null;
  const sample = (String(text).match(re) ?? []).slice(0, 3).join(", ");
  return (
    `Your reply contains words in another writing system (${sample}). The learner is learning ` +
    `${target ?? "the target language"} and reads ${native ?? "her own language"}; she cannot read ` +
    `these. Write the whole turn again using only ${target ?? "the target language"} (and ` +
    `${native ?? "her language"} where the practice allows it), with an ordinary word in their place.`
  );
}

/** Last resort when the rewrite still carries them: drop the characters and tidy. */
export function stripForeignScript(text: string, target?: string, native?: string): string {
  let out = String(text ?? "");
  for (let re = foreignScript(out, target, native); re; re = foreignScript(out, target, native)) {
    out = out.replace(re, "");
  }
  return out
    .replace(/[ \t]+([,.;:!?])/g, "$1")
    .replace(/([,;:])(\s*[,;:])+/g, "$1")
    .replace(/(["“'‘])\s*(["”'’])/g, "")
    .replace(/[ \t]{2,}/g, " ");
}
