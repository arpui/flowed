// fluent_record_answer ↔ the review queue — run with:
//   node --experimental-strip-types server/test/record-item.test.ts
//
// Why this exists, measured on 2026-09-19:
//
// The tool asked the tutor to copy an item id "verbatim from the preloaded
// due-items list". The tutor is never shown that list — the pacing note carries
// the item's CONTENT and nothing else, on purpose, because an invented id
// advances the wrong schedule silently. So every record the tutor wrote came
// back without an item_id, and the only ones that had one were the records the
// server derived when the tutor forgot to call the tool at all. Fix the tutor's
// tool-calling and the review schedule stops being fed: 9 records with an id
// became 0, and nothing failed while it happened.
//
// Same rule as the counter and the marker: what the model must report, the
// server derives. The item that was on screen is the server's own fact.

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

function makeDir(items: string[]): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fluent-record-"));
  fs.writeFileSync(
    path.join(dir, "spaced-repetition.json"),
    JSON.stringify({ items: Object.fromEntries(items.map((id) => [id, { content: id }])) }),
    "utf8"
  );
  return dir;
}

function recordTool(dataDir: string, grading: { id: string } | null) {
  const { definitions } = buildTools({
    root: REPO,
    dataDir: () => dataDir,
    deep: { model: "deep", baseURL: "http://127.0.0.1:1/v1", temperature: 0.2, maxTokens: 10, timeoutMs: 10 },
    gradingItem: () => grading,
  });
  const tool = definitions.find((d) => d.name === "fluent_record_answer");
  if (!tool) throw new Error("fluent_record_answer is not registered");
  return tool;
}

const ANSWER = {
  skill: "vocabulary",
  exercise: 'How do you say "casa" in English?',
  learner_answer: "house",
  score: 10,
};

function records(dir: string): Array<Record<string, unknown>> {
  const f = path.join(dir, ".records");
  return fs
    .readdirSync(f)
    .flatMap((n) => fs.readFileSync(path.join(f, n), "utf8").split("\n"))
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));
}

// 1. the tutor omits item_id and the server knows which item was on screen
{
  const dir = makeDir(["vocabulary_house"]);
  const out = await recordTool(dir, { id: "vocabulary_house" }).execute(
    { ...ANSWER }, { sessionID: "s1", messageID: "m1", dataDir: dir }
  );
  const [rec] = records(dir);
  check("the record carries the server's item", rec?.item_id === "vocabulary_house", rec);
  check("and an SM-2 quality derived from the score", rec?.sm2_quality === 5, rec);
  check("the tutor is told nothing to copy next time", !out.includes("REJECTED"), out);
}

// 2. nothing on screen from the queue: the record stays clean
{
  const dir = makeDir(["vocabulary_house"]);
  await recordTool(dir, null).execute(
    { ...ANSWER }, { sessionID: "s2", messageID: "m2", dataDir: dir }
  );
  const [rec] = records(dir);
  check("a free exercise records no item", rec !== undefined && !("item_id" in rec), rec);
}

// 3. a server item that is NOT in this learner's queue is never written:
//    a stale assignment must not advance someone else's schedule.
{
  const dir = makeDir(["vocabulary_house"]);
  await recordTool(dir, { id: "vocabulary_ghost" }).execute(
    { ...ANSWER }, { sessionID: "s3", messageID: "m3", dataDir: dir }
  );
  const [rec] = records(dir);
  check("an item outside the queue is dropped, not written", rec !== undefined && !("item_id" in rec), rec);
}

// 4. the tutor's own id still wins when it gives one, and is still checked
{
  const dir = makeDir(["vocabulary_house", "vocabulary_water"]);
  await recordTool(dir, { id: "vocabulary_house" }).execute(
    { ...ANSWER, item_id: "vocabulary_water" }, { sessionID: "s4", messageID: "m4", dataDir: dir }
  );
  check("an explicit item_id is kept", records(dir)[0]?.item_id === "vocabulary_water", records(dir)[0]);

  const dir2 = makeDir(["vocabulary_house"]);
  const out = await recordTool(dir2, { id: "vocabulary_house" }).execute(
    { ...ANSWER, item_id: "vocabulary_invented" }, { sessionID: "s5", messageID: "m5", dataDir: dir2 }
  );
  check("an invented item_id is still rejected", out.startsWith("REJECTED"), out);
}

console.log(failures === 0 ? "\nrecord-item: all checks passed" : `\nrecord-item: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
