// Streaming accumulator checks — run with:
//   node --experimental-strip-types server/test/stream-parser.test.ts
// (tests/test_server_stream.py runs this as part of the normal test suite.)
//
// The fragile part of streaming is not the text: it is that llama.cpp sends
// tool_calls in pieces (name in one chunk, arguments split across several,
// addressed by `index`). If they are reassembled wrong, the tool is called with
// broken JSON and the turn dies.

import { newStreamAccumulator, applyStreamChunk, finishStream } from "../src/llm.ts";

let failures = 0;
function check(name: string, cond: boolean, detail?: unknown) {
  if (cond) {
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.error(`  FAIL ${name}${detail === undefined ? "" : ` → ${JSON.stringify(detail)}`}`);
  }
}

function feed(payloads: unknown[]): { acc: ReturnType<typeof newStreamAccumulator>; deltas: string[] } {
  const acc = newStreamAccumulator();
  const deltas: string[] = [];
  for (const p of payloads) {
    const d = applyStreamChunk(acc, typeof p === "string" ? p : JSON.stringify(p));
    if (d) deltas.push(d);
  }
  return { acc, deltas };
}

const textChunk = (content: string) => ({ choices: [{ index: 0, delta: { content } }] });
const stop = { choices: [{ index: 0, delta: {}, finish_reason: "stop" }] };

// 1. plain text
{
  const { acc, deltas } = feed([textChunk("Hola"), textChunk(", "), textChunk("Albert"), stop]);
  const res = finishStream(acc);
  check("text deltas are emitted one by one", deltas.join("") === "Hola, Albert", deltas);
  check("text is assembled", res.choices[0]!.message.content === "Hola, Albert");
  check("finish_reason is kept", res.choices[0]!.finish_reason === "stop");
}

// 2. a tool call split across chunks, the way llama.cpp sends it
{
  const { acc } = feed([
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: "call_1", type: "function", function: { name: "math_record", arguments: "" } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: '{"score"' } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: ": 8, \"item" } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: '_id": "vocab_x"}' } }] } }] },
    { choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }] },
  ]);
  const res = finishStream(acc);
  const tc = res.choices[0]!.message.tool_calls?.[0];
  check("the call has its name", tc?.function.name === "math_record", tc?.function.name);
  check("the arguments are valid JSON", (() => {
    try { return JSON.parse(tc?.function.arguments ?? "").item_id === "vocab_x"; } catch { return false; }
  })(), tc?.function.arguments);
  check("finish_reason is tool_calls", res.choices[0]!.finish_reason === "tool_calls");
}

// 3. two calls interleaved by index
{
  const { acc } = feed([
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: "a", function: { name: "skill", arguments: "{\"na" } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 1, id: "b", function: { name: "bash", arguments: "{\"com" } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: "me\": \"math-learn\"}" } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 1, function: { arguments: "mand\": \"ls\"}" } }] } }] },
  ]);
  const calls = finishStream(acc).choices[0]!.message.tool_calls ?? [];
  check("both calls survive, in index order", calls.length === 2 && calls[0]!.function.name === "skill" && calls[1]!.function.name === "bash", calls.map((c) => c.function.name));
  check("neither set of arguments is mixed up",
    JSON.parse(calls[0]!.function.arguments).name === "math-learn" &&
    JSON.parse(calls[1]!.function.arguments).command === "ls");
}

// 4. noise never throws
{
  const { acc, deltas } = feed(["[DONE]", "", "not json at all", "{\"broken\": ", textChunk("ok")]);
  check("garbage lines are ignored", deltas.join("") === "ok" && finishStream(acc).choices[0]!.message.content === "ok");
}

// 5. usage rides along (stream_options.include_usage)
{
  const { acc } = feed([textChunk("x"), { choices: [], usage: { prompt_tokens: 1200, completion_tokens: 42 } }]);
  const res = finishStream(acc);
  check("usage is captured for the metrics line", (res.usage as any)?.prompt_tokens === 1200);
}

// 6. an empty stream yields an empty answer, not a crash
{
  const res = finishStream(newStreamAccumulator());
  check("empty stream is harmless", res.choices[0]!.message.content === null && res.choices[0]!.finish_reason === "stop");
}

console.log(failures === 0 ? "stream parser: all checks passed" : `stream parser: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
