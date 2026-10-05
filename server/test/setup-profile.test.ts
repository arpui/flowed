// math_setup_profile checks — run with:
//   node --experimental-strip-types server/test/setup-profile.test.ts
//
// This is the tool that made /math-setup finishable at all: before it, the
// interview had nowhere to write. What matters is that it refuses bad input
// clearly (the model has to be able to fix itself) and that a successful call
// leaves a profile the rest of the system can read.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildTools } from "../src/tools.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

const REPO = path.resolve(import.meta.dirname, "..", "..");
const TEMPLATE = path.join(REPO, "data-examples", "learner-profile-template.json");

function makeProfileDir(withProfile = true): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "math-setup-"));
  if (withProfile) fs.copyFileSync(TEMPLATE, path.join(dir, "learner-profile.json"));
  return dir;
}

function setupTool(dataDir: string) {
  const { definitions } = buildTools({
    root: REPO,
    dataDir: () => dataDir,
    deep: { model: "deep", baseURL: "http://127.0.0.1:1/v1", temperature: 0.2, maxTokens: 10, timeoutMs: 10 },
  });
  const tool = definitions.find((d) => d.name === "math_setup_profile");
  if (!tool) throw new Error("math_setup_profile is not registered");
  return tool;
}

const GOOD = {
  name: "Nes",
  target_language: "English",
  native_language: "Catalan",
  current_level: "a2",
  target_level: "B1",
  daily_minutes: 20,
  goals: ["parlar amb els cosins"],
  interests: ["futbol", "dinosaures", "minecraft", "extra que s'ha de retallar"],
};

// 1. the happy path
{
  const dir = makeProfileDir();
  const tool = setupTool(dir);
  const out = await tool.execute(GOOD, { sessionID: "s", messageID: "m", dataDir: dir });
  check("a complete interview is accepted", out.startsWith("profile saved"), out);

  const profile = JSON.parse(fs.readFileSync(path.join(dir, "learner-profile.json"), "utf8"));
  check("the name is stored", profile.learner.name === "Nes");
  check("languages are stored", profile.learner.target_language === "English" && profile.learner.native_language === "Catalan");
  check("a lowercase level is normalized", profile.learner.current_level === "A2", profile.learner.current_level);
  check("daily minutes are stored", profile.learner.daily_goal_minutes === 20);
  check("goals land in focus_areas", Array.isArray(profile.focus_areas) && profile.focus_areas[0] === "parlar amb els cosins");
  check("interests are capped at 3", profile.learner.interests.length === 3, profile.learner.interests);
  check("setup is marked complete", profile.preferences.setup_complete === true);
  // A placeholder is a STRING VALUE shaped like "{...}" — not the object braces.
  const placeholders = JSON.stringify(profile.learner).match(/"\{[^"]*\}"/g) ?? [];
  check("template placeholders are gone", placeholders.length === 0, placeholders);
  check("the date placeholder in achievements is filled", !JSON.stringify(profile.achievements).includes("{YYYY"));
  const backups = fs.readdirSync(dir).filter((f) => f.includes(".backup-"));
  check("the previous profile was backed up", backups.length === 1, backups);
  const leftovers = fs.readdirSync(dir).filter((f) => f.endsWith(".tmp"));
  check("no temporary file is left behind", leftovers.length === 0, leftovers);
}

// 2. the rejections a model must be able to act on
{
  const dir = makeProfileDir();
  const tool = setupTool(dir);
  const ctx = { sessionID: "s", messageID: "m", dataDir: dir };

  const same = await tool.execute({ ...GOOD, native_language: "English" }, ctx);
  check("same language twice is rejected", same.startsWith("REJECTED") && same.includes("which one"), same);

  const level = await tool.execute({ ...GOOD, current_level: "beginner" }, ctx);
  check("a non-CEFR level is rejected, listing the valid ones", level.startsWith("REJECTED") && level.includes("A1, A2"), level);

  const noName = await tool.execute({ ...GOOD, name: "  " }, ctx);
  check("an empty name is rejected", noName.startsWith("REJECTED"), noName);

  const untouched = JSON.parse(fs.readFileSync(path.join(dir, "learner-profile.json"), "utf8"));
  check("a rejected call writes nothing", untouched.learner.name === "{YOUR_NAME}", untouched.learner.name);
}

// 3. no profile directory: the owner has to create it, and the message says so
{
  const dir = makeProfileDir(false);
  const out = await setupTool(dir).execute(GOOD, { sessionID: "s", messageID: "m", dataDir: dir });
  check("a missing profile is a clear refusal", out.startsWith("REJECTED") && out.includes("new-user.sh"), out);
}

// 4. minutes are clamped, not trusted
{
  const dir = makeProfileDir();
  await setupTool(dir).execute({ ...GOOD, daily_minutes: 9000 }, { sessionID: "s", messageID: "m", dataDir: dir });
  const profile = JSON.parse(fs.readFileSync(path.join(dir, "learner-profile.json"), "utf8"));
  check("absurd daily minutes are clamped", profile.learner.daily_goal_minutes === 240, profile.learner.daily_goal_minutes);
}

console.log(failures === 0 ? "setup profile: all checks passed" : `setup profile: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
