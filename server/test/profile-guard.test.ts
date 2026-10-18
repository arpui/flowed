// Cross-profile guard (docs/ENCARREC-P4-FLASH-INICI.md §4): a tab still open on another profile gets 409 from
// the server before any handler runs, and writes nothing. Runs under node (--experimental-strip-types) and bun.
// The real-server part starts server/src/index.ts with bun (the server needs it) on a temporary profile dir.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { profileMismatch } from "../src/profile.ts";

let fails = 0;
const check = (name: string, cond: boolean, extra?: unknown) => {
  console.log(`${cond ? "  ok  " : "  FAIL"} ${name}${cond || extra === undefined ? "" : " -> " + JSON.stringify(extra)}`);
  if (!cond) fails++;
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

console.log("profile guard");
const req = (url: string, headers: Record<string, string> = {}) => new Request(url, { headers });
{
  const r = profileMismatch(req("http://x/api/flash/state", { "x-flowed-profile": "beta" }), "alpha");
  check("header of another profile: 409 profile_mismatch", !!r && r.status === 409 && r.headers.get("content-type") === "application/json");
  const body = r ? await r.text() : "";
  check("the 409 body names profile_mismatch", body === '{"error":"profile_mismatch"}', body);
  check("header of the same profile: served as before", profileMismatch(req("http://x/api/flash/state", { "x-flowed-profile": "alpha" }), "alpha") === null);
  check("no header (direct calls, old pages): served as before", profileMismatch(req("http://x/api/flash/state"), "alpha") === null);
  check("SSE with ?profile= of another profile: 409", profileMismatch(req("http://x/api/event?profile=beta"), "alpha")?.status === 409);
  check("SSE with ?profile= of the same profile: served", profileMismatch(req("http://x/api/event?profile=alpha"), "alpha") === null);
  check("the header wins over a query of the same profile", profileMismatch(req("http://x/api/event?profile=alpha", { "x-flowed-profile": "beta" }), "alpha")?.status === 409);
}

// The real server: a stale write is refused and nothing lands on disk.
console.log("real server");
const bunBin = process.env.BUN || "bun";
const hasBun = spawnSync(bunBin, ["--version"]).status === 0;
if (!hasBun) {
  console.log("  skip  bun is not installed: the real-server part did not run");
} else {
  const root = path.resolve(import.meta.dirname, "..", "..");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-"));
  const dataDir = path.join(tmp, "alpha");
  fs.mkdirSync(dataDir);
  fs.writeFileSync(path.join(dataDir, "learner-profile.json"), JSON.stringify({ learner: { name: "Alpha", current_level: "m5", target_language: "Math" } }));
  fs.writeFileSync(path.join(dataDir, ".web-password"), "pw\n");
  const port: number = await new Promise((resolve) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const p = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(p));
    });
  });
  const proc = spawn(bunBin, [path.join(root, "server", "src", "index.ts")], {
    cwd: root,
    env: { ...process.env, PORT: String(port), FLOWED_DATA_DIR: dataDir, FLOWED_WEB_PASSWORD: "pw" },
    stdio: "ignore",
  });
  const auth = "Basic " + Buffer.from("alpha:pw").toString("base64");
  const base = `http://127.0.0.1:${port}`;
  try {
    for (let i = 0; i < 100; i++) {
      try {
        if ((await fetch(base + "/api/global/health")).ok) break;
      } catch { /* not up yet */ }
      await sleep(100);
    }
    const put = (headers: Record<string, string>) =>
      fetch(base + "/api/flash/state", { method: "PUT", headers: { authorization: auth, "content-type": "application/json", ...headers }, body: JSON.stringify({ version: 1, lists: {} }) });
    const stale = await put({ "x-flowed-profile": "beta" });
    check("stale tab (beta) writes to alpha: 409", stale.status === 409, stale.status);
    check("stale write leaves no flash-db.json behind", !fs.existsSync(path.join(dataDir, "flash-db.json")));
    const own = await put({ "x-flowed-profile": "alpha" });
    check("own profile header: the write goes through", own.status === 200, own.status);
    check("own write is on disk", fs.existsSync(path.join(dataDir, "flash-db.json")));
    fs.rmSync(path.join(dataDir, "flash-db.json"));
    const sse = await fetch(base + "/api/event?profile=beta", { headers: { authorization: auth } });
    check("SSE of another profile: 409 before the stream", sse.status === 409, sse.status);
    sse.body?.cancel().catch(() => {});
  } finally {
    proc.kill("SIGKILL");
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}
console.log(fails ? `${fails} FAILED` : "profile guard: all ok");
if (fails) process.exit(1);
