// The web shell per domain — run with:
//   node --experimental-strip-types server/test/domain-shell.test.ts
//
// 2026-10-08 (Albert, first 0.6 look at llvm): a language profile (nes-en)
// opened as "FlowMath", with a "Vocabulary" button and Go labelled "Surprise
// me!". The language bar is the 0.5 one: Go, Review, Reading (above A1),
// Writing, Speaking, Stats, End — Vocabulary lives inside Go.

import fs from "node:fs";
import path from "node:path";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

const root = path.join(import.meta.dirname, "..", "..");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "config", "domain.json"), "utf8"));
const http = fs.readFileSync(path.join(root, "server", "src", "http.ts"), "utf8");
const app = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

check("language brand is FlowEd", manifest.domains.language.brand === "FlowEd");
check("math brand is FlowEd too (one app, two domains)", manifest.domains.math.brand === "FlowEd");
check("domain labels Language / Math", manifest.domains.language.domain_label === "Language" && manifest.domains.math.domain_label === "Math");
check("math hides Facts via manifest, language does not", (manifest.domains.math.hidden_commands || []).includes("math-vocab") && !(manifest.domains.language.hidden_commands || []).length);
check("http.ts injects hidden commands + domain label", http.includes("__FLOWED_HIDDEN") && http.includes("domain_label"));
check("both domains have a favicon", !!manifest.domains.language.favicon && !!manifest.domains.math.favicon);
check("http.ts injects title, brand and icon from the manifest",
  /<title>\$\{brand\}/.test(http) && http.includes("__FLOWED_BRAND") && http.includes("favicon"));

const labels = app.slice(app.indexOf("const LANG_LABELS"), app.indexOf("// Open practices the profile"));
const labelMap = labels.slice(0, labels.indexOf("};"));
check("Go is labelled Go, not Surprise me!", labelMap.includes('"Go"') && !/Surprise/.test(labels));
check("no Vocabulary button in language", labels.includes('key === "math-vocab"') && !/math-vocab|Vocabulary/.test(labelMap));
check("language bar uses the 0.5 labels", labels.includes('"Stats"') && labels.includes('"End"') && labels.includes('"Reading"'));
check("Reading unlocks above A1 in language", /L_ORDER\.indexOf\(lv\) >= 1/.test(app));
check("no first-use thinking hint (it showed cut off under the header)", !/showThinkingTip|comptador desapareix/.test(app));

if (failures) {
  console.log(`\n${failures} FAILED`);
  process.exit(1);
}
check("command prompts of BOTH prefixes collapse to a chip (/fluent-end leaked its instructions)",
  /Execute\\s\+\\\/\(\(\?:math\|fluent\)-/.test(app) || app.includes("(?:math|fluent)-"));

console.log("\nall ok");
