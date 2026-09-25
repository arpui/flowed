// A session from before a server restart is not resumed — run with:
//   node --experimental-strip-types server/test/session-resume.test.ts
//
// 2026-09-25: after restarting the app, the web showed the last session with
// its pending question. The answer was not graded: the question lived only in
// the previous process's memory, so the server moved on to a new one.

import { resumeState } from "../src/session.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

const BOOT = 1_000_000_000;
const IDLE = 30 * 60 * 1000;
const now = BOOT + 5 * 60 * 1000;

let s = resumeState({ last_activity: BOOT + 60_000, metadata: null }, now, BOOT, IDLE);
check("a session used since this start resumes", s.resumable && s.reason === "ok", s);

s = resumeState({ last_activity: BOOT - 60_000, metadata: null }, now, BOOT, IDLE);
check("a session last used before the restart does not", !s.resumable && s.restarted && s.reason === "restart", s);

s = resumeState({ last_activity: BOOT + 60_000, metadata: JSON.stringify({ capa_b_done: 1 }) }, now, BOOT, IDLE);
check("finalized wins over everything", !s.resumable && s.reason === "finalized", s);

s = resumeState({ last_activity: BOOT + 60_000, metadata: null }, BOOT + 60_000 + IDLE + 1, BOOT, IDLE);
check("idle past the limit does not resume", !s.resumable && s.reason === "idle", s);

s = resumeState({ last_activity: BOOT + 60_000, metadata: "{bad" }, now, BOOT, IDLE);
check("malformed metadata still resumes", s.resumable, s);

console.log(failures === 0 ? "\nsession-resume: all checks passed" : `\nsession-resume: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
