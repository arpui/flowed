// Text-to-speech checks — run with:
//   node --experimental-strip-types server/test/tts.test.ts
//
// The risky part of TTS is not the synthesis, it is WHAT gets spoken: the text
// arrives from a rendered chat bubble carrying markdown, emoji, scores and the
// tutor's asides in the learner's NATIVE language. An English voice reading a
// Catalan parenthesis teaches the wrong thing, so the cleaning is the part
// worth pinning down. The rest is refusing to guess a voice and not filling
// the disk.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  speakableText,
  cacheKey,
  voiceFor,
  resolveTtsConfig,
  validate,
  pruneCache,
  MAX_TTS_CHARS,
  DEFAULT_TTS,
  ttsEnv,
  loadTtsConfig,
  ttsDirFor,
  voiceLanguage,
} from "../src/tts.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

// --- what gets spoken -------------------------------------------------------

check("markdown emphasis goes",
  speakableText("**I have been waiting**") === "I have been waiting",
  speakableText("**I have been waiting**"));

check("a native-language aside goes",
  speakableText("I have been waiting (fa estona que espero)") === "I have been waiting",
  speakableText("I have been waiting (fa estona que espero)"));

check("the score goes",
  speakableText("Nice work 8/10") === "Nice work",
  speakableText("Nice work 8/10"));

check("emoji go",
  speakableText("Good morning! 👋 🔥") === "Good morning!",
  speakableText("Good morning! 👋 🔥"));

check("a machine block never reaches the voice",
  !speakableText("Say this\n```fluent:review_results\nid: 3\n```").includes("review_results"));

check("code marks go but the word stays",
  speakableText("the verb `to be`") === "the verb to be",
  speakableText("the verb `to be`"));

check("a link keeps its label, not its url",
  speakableText("see [the rule](https://example.com/x)") === "see the rule",
  speakableText("see [the rule](https://example.com/x)"));

check("whitespace is collapsed",
  speakableText("  a    b \n\n c ") === "a b c",
  speakableText("  a    b \n\n c "));

check("nothing to say is empty, not a subprocess", speakableText("   \n  ") === "");
check("emoji-only is empty too", speakableText("🔊 👋") === "");
check("a runaway string is cut", speakableText("x".repeat(5000)).length === MAX_TTS_CHARS);
check("null does not throw", speakableText(null as unknown as string) === "");

// --- the cache --------------------------------------------------------------

check("the same sentence is the same file",
  cacheKey("Good morning", "alba") === cacheKey("Good morning", "alba"));
check("a different voice is a different file",
  cacheKey("Good morning", "alba") !== cacheKey("Good morning", "lessac"));
check("a different sentence is a different file",
  cacheKey("Good morning", "alba") !== cacheKey("Good evening", "alba"));

// --- the voice: never a guess ----------------------------------------------

{
  const cfg = resolveTtsConfig({
    enabled: true,
    binary: "/opt/piper/piper",
    voices: { English: "/voices/en_GB-alba-medium.onnx" },
    cache_max_mb: 50,
  });
  check("the config is read", cfg.enabled && cfg.binary === "/opt/piper/piper" && cfg.cacheMaxMb === 50, cfg);
  check("language lookup is case-insensitive",
    voiceFor(cfg, "english") === "/voices/en_GB-alba-medium.onnx");
  check("a language with no voice gets none, not the wrong one",
    voiceFor(cfg, "German") === null);
  check("no language, no voice", voiceFor(cfg, undefined) === null);

  const off = resolveTtsConfig({ voices: { English: "/v.onnx" } });
  check("disabled unless explicitly enabled", off.enabled === false);
  check("a missing config block is off", resolveTtsConfig(undefined).enabled === false);
  check("defaults are sane", DEFAULT_TTS.enabled === false && DEFAULT_TTS.cacheMaxMb > 0);

  const r1 = validate(off, { text: "hello", language: "English" });
  check("a disabled engine refuses with 503",
    "ok" in r1 && r1.ok === false && r1.status === 503, r1);
  const r2 = validate(cfg, { text: "   ", language: "English" });
  check("nothing to say refuses with 400",
    "ok" in r2 && r2.ok === false && r2.status === 400, r2);
  const r3 = validate(cfg, { text: "hello", language: "German" });
  check("an unknown language refuses rather than guessing",
    "ok" in r3 && r3.ok === false && r3.status === 503, r3);
  const r4 = validate(cfg, { text: "hello", language: "English" });
  check("a voice file that is not there refuses too",
    "ok" in r4 && r4.ok === false && String(r4.error).includes("not found"), r4);
}

// --- the cache does not eat the disk ---------------------------------------

{
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fluent-tts-"));
  const kb = Buffer.alloc(1024 * 300, 1); // 300 KB each
  for (let i = 0; i < 5; i++) {
    const f = path.join(dir, `${i}.wav`);
    fs.writeFileSync(f, kb);
    fs.utimesSync(f, new Date(1000 + i * 1000), new Date(1000 + i * 1000));
  }
  const removed = pruneCache(dir, 1); // 1 MB budget, 1.5 MB present
  const left = fs.readdirSync(dir).filter((f) => f.endsWith(".wav")).sort();
  check("over budget, the oldest go", removed >= 2, { removed, left });
  check("the newest survive", left.includes("4.wav") && !left.includes("0.wav"), left);
  check("under budget, nothing is touched", pruneCache(dir, 500) === 0);
  check("a missing cache dir is not an error", pruneCache(path.join(dir, "nope"), 1) === 0);
  fs.rmSync(dir, { recursive: true, force: true });
}

// --- piper must not depend on whoever started the server --------------------
// It ships its own libespeak-ng and libonnxruntime next to the binary. Fixing
// that in ~/.bashrc works until the server is started by systemd, cron, or on
// another machine — and then the speaker buttons 503 with nothing in the log.

{
  const BIN = "/home/x/.fluent/_tts/piper/piper";
  const env = ttsEnv(BIN, {});
  check("the loader is pointed at piper's own directory",
    env.LD_LIBRARY_PATH === "/home/x/.fluent/_tts/piper", env.LD_LIBRARY_PATH);
  check("espeak data is found next to the binary",
    env.ESPEAK_DATA_PATH === "/home/x/.fluent/_tts/piper/espeak-ng-data", env.ESPEAK_DATA_PATH);

  const kept = ttsEnv(BIN, { LD_LIBRARY_PATH: "/usr/lib:/opt/lib" });
  check("an existing LD_LIBRARY_PATH is kept, not replaced",
    kept.LD_LIBRARY_PATH === "/home/x/.fluent/_tts/piper:/usr/lib:/opt/lib", kept.LD_LIBRARY_PATH);

  const twice = ttsEnv(BIN, { LD_LIBRARY_PATH: "/home/x/.fluent/_tts/piper:/usr/lib" });
  check("the directory is not added twice",
    twice.LD_LIBRARY_PATH === "/home/x/.fluent/_tts/piper:/usr/lib", twice.LD_LIBRARY_PATH);

  const respected = ttsEnv(BIN, { ESPEAK_DATA_PATH: "/somewhere/else" });
  check("an explicit ESPEAK_DATA_PATH wins",
    respected.ESPEAK_DATA_PATH === "/somewhere/else");

  check("a binary on PATH is left alone (the system packaged it)",
    ttsEnv("piper", {}).LD_LIBRARY_PATH === undefined);

  check("the rest of the environment survives",
    ttsEnv(BIN, { HOME: "/home/x" }).HOME === "/home/x");
}

// --- this machine's install, found on disk (2026-09-26) ---------------------
// config/fluent.json travels between machines; piper does not. Paths to it in
// the shared config broke audio after `mv ~/.fluent ~/.flowed` and after a
// rsync to llvm.
{
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "tts-home-"));
  const tts = path.join(home, ".flowed", "_tts");
  fs.mkdirSync(path.join(tts, "piper"), { recursive: true });
  fs.mkdirSync(path.join(tts, "voices"), { recursive: true });
  fs.writeFileSync(path.join(tts, "piper", "piper"), "");
  for (const f of ["en_GB-alba-medium.onnx", "en_GB-alba-medium.onnx.json", "de_DE-thorsten-low.onnx"]) {
    fs.writeFileSync(path.join(tts, "voices", f), "");
  }
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), "tts-repo-"));
  fs.mkdirSync(path.join(repo, "config"));
  const writeCfg = (t: unknown) => fs.writeFileSync(path.join(repo, "config", "fluent.json"), JSON.stringify({ tts: t }));
  const profile = path.join(home, ".flowed", "nes-en");

  check("voice file names map to the profile's language",
    voiceLanguage("en_GB-alba-medium.onnx") === "English" && voiceLanguage("xx.onnx") === null);
  check("the _tts folder is found next to the profile",
    ttsDirFor(profile, {}, home) === tts);
  check("…and by the profiles-folder rule without a profile",
    ttsDirFor(undefined, {}, home) === tts);
  check("$FLOWED_TTS_DIR wins",
    ttsDirFor(profile, { FLOWED_TTS_DIR: repo }, home) === repo);

  writeCfg({ enabled: true, binary: "/home/albert/.fluent/_tts/piper/piper",
    voices: { English: "/home/albert/.fluent/_tts/voices/en_GB-alba-medium.onnx" } });
  let c = loadTtsConfig(repo, profile, tts);
  check("stale paths in the config give way to what is on disk",
    c.enabled && c.binary === path.join(tts, "piper", "piper")
      && voiceFor(c, "English") === path.join(tts, "voices", "en_GB-alba-medium.onnx"), c);
  check("a voice without its .onnx.json is not offered", voiceFor(c, "German") === null);

  writeCfg({ enabled: true });
  c = loadTtsConfig(repo, profile, tts);
  check("enabled + nothing named = this machine's install", c.enabled && voiceFor(c, "english") !== null, c);

  writeCfg({ enabled: false });
  check("the config can still switch it off", loadTtsConfig(repo, profile, tts).enabled === false);

  writeCfg({ enabled: true });
  check("enabled but nothing installed stays off", loadTtsConfig(repo, profile, null).enabled === false);

  fs.rmSync(home, { recursive: true, force: true });
  fs.rmSync(repo, { recursive: true, force: true });
}

console.log(failures === 0 ? "tts: all checks passed" : `tts: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
