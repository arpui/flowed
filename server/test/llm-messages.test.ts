// Late system messages vs strict chat templates — run with:
//   node --experimental-strip-types server/test/llm-messages.test.ts
//
// 2026-09-27: a 27B behind TabbyAPI answered every exercise with
// "TemplateError: System message must be at the beginning." — the server puts
// the per-turn note as a system message at the end of the history.

import { foldLateSystem, LATE_SYSTEM_REFUSED } from "../src/llm.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) console.log(`  ok   ${name}`);
  else {
    failures++;
    console.log(`  FAIL ${name}`, detail ?? "");
  }
}

const sys = (c: string) => ({ role: "system", content: c });
const user = (c: string) => ({ role: "user", content: c });
const asst = (c: string) => ({ role: "assistant", content: c });

const c = (msgs: Array<{ content: string | null }>, i: number) => msgs[i]?.content ?? "";

let out = foldLateSystem([sys("rules"), user("hi"), asst("Q1"), user("my answer"), sys("pacing note")]);
check("only the first message is system", out.filter((m) => m.role === "system").length === 1 && out[0]?.role === "system", out);
check("the note joins the learner's last turn, marked", out.length === 4 && out[3]?.role === "user"
  && c(out, 3).startsWith("my answer") && c(out, 3).includes("not written by the learner")
  && c(out, 3).includes("pacing note"), out);

out = foldLateSystem([sys("rules"), user("x"), asst("draft"), sys("retry: fix it")]);
check("after the tutor's turn it becomes a user turn of its own", out.length === 4 && out[3]?.role === "user", out);

out = foldLateSystem([sys("a"), sys("b"), user("x")]);
check("leading system messages merge into one", out.length === 2 && c(out, 0) === "a\n\nb", out);

const plain = [sys("rules"), user("x"), asst("y")];
check("nothing to fold, nothing changes", JSON.stringify(foldLateSystem(plain)) === JSON.stringify(plain));

check("TabbyAPI's refusal is recognised",
  LATE_SYSTEM_REFUSED.test('LLM HTTP 400: {"detail":"TemplateError: System message must be at the beginning."}'));
check("an unrelated 400 is not", !LATE_SYSTEM_REFUSED.test("LLM HTTP 400: context length exceeded"));

console.log(failures === 0 ? "\nllm-messages: all checks passed" : `\nllm-messages: ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
