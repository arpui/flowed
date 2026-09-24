// Fluent server — command loader.
// Parses `prompts/commands/fluent-*.md`: splits YAML frontmatter from the
// body, resolves the directive lines (`` !`cmd` ``) by executing them and
// splicing their output in place, and exposes the agent/model routing.

import fs from "node:fs";
import path from "node:path";
import * as yaml from "js-yaml";
import { renderSkillForModel, requiredSkills } from "./pacing.ts";

export interface ResolvedCommand {
  command: string; // e.g. "fluent-learn"
  agent: string; // agent id from frontmatter (tutor | tutor-fast) or "learner"
  title: string; // first heading/description
  body: string; // expanded body (directives spliced in)
  skill?: { name: string; body: string }; // the SKILL.md that governs it
  state?: string; // the learner-state block the directives printed
}

/**
 * The skill that goes with a command, read from disk.
 *
 * It used to be the model's job to fetch this, through the `skill` tool,
 * because the command's first line said so. That worked only while the command
 * was the first thing in a session. From the second command on the model was
 * already mid-practice and simply carried on without loading anything — and
 * the entire grading contract (the 🔴/🟡/🟢 marker, "Correct version",
 * "Score: N/10") lives in `skills/fluent-review/SKILL.md`. Measured on a real
 * lesson: 🎓 Lesson pressed after the session's automatic /fluent-learn, skill
 * never loaded, no corrections shown, nothing for the counter to read, and the
 * tutor repeating one exercise for twenty-five turns.
 *
 * So the server loads it. Same rule as everywhere else here: what the model has
 * to remember, the server remembers — and what the model has to load, the
 * server loads.
 */
function readSkillFile(root: string, name: string): string | undefined {
  if (!/^fluent-[a-z0-9-]+$/.test(name)) return undefined;
  try {
    const body = fs.readFileSync(path.join(root, "skills", name, "SKILL.md"), "utf8").trim();
    return body || undefined;
  } catch {
    return undefined;
  }
}

/** The two language names, from the learner profile, for the placeholders the
 *  server can actually resolve. */
function profileLanguages(dataDir: string): { target?: string; native?: string } {
  try {
    const p = JSON.parse(fs.readFileSync(path.join(dataDir, "learner-profile.json"), "utf8"));
    return {
      target: p?.learner?.target_language,
      native: p?.learner?.native_language,
    };
  } catch {
    return {};
  }
}

export function loadSkill(
  root: string,
  name: string,
  dataDir?: string
): { name: string; body: string } | undefined {
  const main = readSkillFile(root, name);
  if (!main) return undefined;
  const langs = dataDir ? profileLanguages(dataDir) : undefined;

  // Skills reference each other in prose — "Use the `fluent-feedback-formatter`
  // skill for per-answer feedback" — which is one more hop the model is
  // supposed to take with the skill tool, and does not. The feedback template
  // is in that second file, so the grading contract was two loads away from a
  // model that would not do one. `requires:` in the frontmatter makes the
  // dependency explicit and the server follows it. One level, no cycles.
  const parts = [renderSkillForModel(main, langs)];
  const seen = new Set([name]);
  for (const dep of requiredSkills(main)) {
    if (seen.has(dep)) continue;
    seen.add(dep);
    const body = readSkillFile(root, dep);
    if (!body) continue;
    parts.push(
      `<skill_content name="${dep}">\n${renderSkillForModel(body, langs)}\n</skill_content>`
    );
  }
  return { name, body: parts.join("\n\n") };
}

const SKIPPED_DIRECTIVE_NOTE = "(Learner state: in your system prompt, above. Do NOT reload it.)";

/** Find every `!`cmd` directive line and solve it, returning the expanded body.
 *
 *  With `skip`, the directives are NOT executed and each one is replaced by a
 *  short note. The state block that `read-db.py` prints is the single biggest
 *  chunk of a command, and re-injecting it on the second and third command of
 *  the same session buys nothing but context.
 */
export async function expandDirectives(
  body: string,
  opts: {
    root: string;
    dataDir: string;
    env: Record<string, string | undefined>;
    skip?: boolean;
    /** Collects what the directives printed, so the caller can put it in the
     *  system prompt instead of the history. */
    collect?: string[];
  }
): Promise<string> {
  const lines = body.split("\n");
  const out: string[] = [];
  let noted = false;
  for (const line of lines) {
    const m = /^!`([^`]+)`\s*$/.exec(line);
    if (!m) {
      out.push(line);
      continue;
    }
    if (opts.skip) {
      if (!noted) {
        out.push(SKIPPED_DIRECTIVE_NOTE);
        noted = true;
      }
      continue;
    }
    const cmd = m[1]!;
    try {
      const env: Record<string, string> = {};
      for (const [k, v] of Object.entries(opts.env)) if (typeof v === "string") env[k] = v;
      env["FLUENT_DATA_DIR"] = opts.dataDir;
      env["FLUENT_PROJECT_DIR"] = opts.root;
      env["FLUENT_ROOT"] = opts.root;
      const proc = Bun.spawn(["bash", "-c", cmd], {
        cwd: opts.root,
        env,
        stdout: "pipe",
        stderr: "pipe",
      });
      const exit = await proc.exited;
      const stdout = await new Response(proc.stdout).text();
      const stderr = await new Response(proc.stderr).text();
      // The learner state goes to the SYSTEM prompt, not into the turn. In the
      // history it is a message like any other, and the history is pruned
      // oldest-first when the context fills — so the block naming the learner,
      // their level, their due queue and their weak patterns is the FIRST
      // thing to be dropped from a long session, while the command that
      // follows says "it is in the history above; do NOT reload it". That
      // sentence then sends a tutor into a lesson knowing nothing about who it
      // is teaching.
      if (opts.collect) opts.collect.push(stdout.trimEnd());
      else out.push(stdout.trimEnd());
      if (stderr.trim() && exit !== 0) out.push(`[stderr] ${stderr.trim()}`);
    } catch (e) {
      out.push(`[directive error: ${e instanceof Error ? e.message : String(e)}]`);
    }
  }
  return out.join("\n");
}

export async function loadCommand(
  command: string,
  opts: { root: string; dataDir: string; env: Record<string, string | undefined>; skipDirectives?: boolean }
): Promise<ResolvedCommand | null> {
  const file = path.join(opts.root, "prompts", "commands", `${command}.md`);
  if (!fs.existsSync(file)) return null;
  const raw = fs.readFileSync(file, "utf8");

  // Split frontmatter (leading `---\n ... \n---`).
  let frontmatter: Record<string, unknown> = {};
  let body = raw;
  if (raw.startsWith("---")) {
    const end = raw.indexOf("\n---", 4);
    if (end !== -1) {
      const fmText = raw.slice(4, end);
      try {
        frontmatter = (yaml.load(fmText) as Record<string, unknown>) ?? {};
      } catch {
        frontmatter = {};
      }
      body = raw.slice(end + 4);
    }
  }

  const agent = (frontmatter["agent"] as string) || "learner";
  const description = (frontmatter["description"] as string) || "";
  // `skip` — not `skipDirectives`. The option was declared on loadCommand and
  // then never forwarded, so every command of a session re-ran read-db.py and
  // re-injected the whole state block: +2.8k tokens per press, measured.
  const collected: string[] = [];
  const expanded = await expandDirectives(body, {
    ...opts, skip: opts.skipDirectives, collect: collected,
  });
  const state = collected.join("\n").trim();
  const title = description || `Execute ${command} now:`;

  return {
    command, agent, title, body: expanded,
    skill: loadSkill(opts.root, command, opts.dataDir),
    ...(state ? { state } : {}),
  };
}
