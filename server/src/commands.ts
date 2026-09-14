// Fluent server — command loader.
// Parses `prompts/commands/fluent-*.md`: splits YAML frontmatter from the
// body, resolves the directive lines (`` !`cmd` ``) by executing them and
// splicing their output in place, and exposes the agent/model routing.

import fs from "node:fs";
import path from "node:path";
import * as yaml from "js-yaml";

export interface ResolvedCommand {
  command: string; // e.g. "fluent-learn"
  agent: string; // agent id from frontmatter (tutor | tutor-fast) or "learner"
  title: string; // first heading/description
  body: string; // expanded body (directives spliced in)
}

const SKIPPED_DIRECTIVE_NOTE =
  "(Learner state: already loaded earlier in this session — it is in the history above. " +
  "Do NOT reload it; it has not changed.)";

/** Find every `!`cmd` directive line and solve it, returning the expanded body.
 *
 *  With `skip`, the directives are NOT executed and each one is replaced by a
 *  short note. The state block that `read-db.py` prints is the single biggest
 *  chunk of a command, and re-injecting it on the second and third command of
 *  the same session buys nothing but context.
 */
export async function expandDirectives(
  body: string,
  opts: { root: string; dataDir: string; env: Record<string, string | undefined>; skip?: boolean }
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
      out.push(stdout.trimEnd());
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
  const expanded = await expandDirectives(body, opts);
  const title = description || `Execute ${command} now:`;

  return { command, agent, title, body: expanded };
}
