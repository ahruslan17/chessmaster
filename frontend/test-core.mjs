// No test framework or network. Compile api/client.ts and engineScore.ts as CommonJS
// into an isolated directory with package.json {"type":"commonjs"}, then:
// node frontend/test-core.mjs <compiled-directory>
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const compiled = resolve(process.argv[2]);
const { createSseParser } = require(resolve(compiled, "api/sse.js"));
const { presentScore } = require(resolve(compiled, "engineScore.js"));
const api = require(resolve(compiled, "api/client.js"));

const input = ": comment\r\ndata: first  \r\ndata:second\r\n\r\ndata:  \r\n\r\ndata:\n\ndata: last ";
const expected = ["first  \nsecond", " ", "", "last "];
for (let split = 0; split <= input.length; split += 1) {
  const events = [];
  const parser = createSseParser((event) => events.push(event));
  parser.push(input.slice(0, split));
  parser.push(input.slice(split));
  parser.finish();
  assert.deepEqual(events, expected, `SSE split ${split}`);
}
{
  const events = [];
  const parser = createSseParser((event) => events.push(event));
  for (const character of "data: a\r\rdata: b\r\n\r\ndata\n\n") parser.push(character);
  parser.finish();
  assert.deepEqual(events, ["a", "b", ""]);
}

const score = (fields) => ({ cp: null, mate: null, mate_winner: null, perspective: "white", ...fields });
assert.equal(presentScore(score({ cp: 1500 })).label, "+15.0");
assert.equal(presentScore(score({ cp: -1500 })).label, "-15.0");
assert.equal(presentScore(score({ mate: -3 })).label, "−M3");
assert.equal(presentScore(score({ mate: 0, mate_winner: "black" })).whitePercent, 0);
assert.equal(presentScore(score({ mate: 0, mate_winner: "white" })).whitePercent, 100);
assert.equal(presentScore(score({ mate: 0 })).label, "—");
assert.equal(presentScore(null).label, "—");
assert.equal(presentScore({ cp: 0 }).label, "—");
assert.equal(presentScore(score({ cp: 0 })).label, "0.0");

const requests = [];
globalThis.fetch = async (url, options) => {
  requests.push({ url, options });
  return Response.json({ game_id: "game", status: "queued" });
};
await api.getAnalysis("game", "black");
await api.getAnalysisStatus("game", "white");
assert.equal(requests[0].url, "/api/games/game/analysis?player_color=black");
assert.equal(requests[1].url, "/api/games/game/analysis/status?player_color=white");
assert.equal(requests[0].options.method, undefined);
await api.startAnalysis("game", true, "engine-attempt");
await api.startExplanations("game", "black", true, "review-attempt");
await api.startExplanations("game", "white");
assert.deepEqual(JSON.parse(requests[2].options.body), { recover: true, expected_attempt_id: "engine-attempt" });
assert.deepEqual(JSON.parse(requests[3].options.body), { player_color: "black", recover: true, expected_attempt_id: "review-attempt" });
assert.deepEqual(JSON.parse(requests[4].options.body), { player_color: "white", recover: false });
assert.equal(requests[2].options.method, "POST");
await api.uploadPgn(new Blob(["1. e4 *"], { type: "text/plain" }), "black");
assert.equal(requests[5].url, "/api/games/upload?player_color=black");
assert.equal(requests[5].options.body.get("player_color"), "black");
await api.startExplanations("game", "black", false, undefined, true);
await api.startExplanations("game", "white", true, "upgrade-attempt", true);
assert.deepEqual(JSON.parse(requests[6].options.body), { player_color: "black", recover: false, detailed: true });
assert.deepEqual(JSON.parse(requests[7].options.body), { player_color: "white", recover: true, expected_attempt_id: "upgrade-attempt", detailed: true });

const chunks = [];
globalThis.fetch = async () => new Response(new ReadableStream({
  start(controller) {
    for (const byte of new TextEncoder().encode("data: Привет \r\n\r\ndata:  \n\ndata: мир\n\n")) {
      controller.enqueue(Uint8Array.of(byte));
    }
    controller.close();
  },
}));
assert.equal(await api.streamMoveCommentary("game", 0, (chunk) => chunks.push(chunk)), "Привет  мир");
assert.deepEqual(chunks, ["Привет ", " ", "мир"]);
globalThis.fetch = async () => new Response(new ReadableStream({
  start(controller) {
    controller.enqueue(Uint8Array.from([...new TextEncoder().encode("data: "), 0xd0]));
    controller.close();
  },
}));
assert.equal(await api.streamMoveCommentary("game", 0), "�", "flush incomplete UTF-8 at EOF");

globalThis.fetch = async () => Response.json({ detail: { message: "Попытка уже заменена" } }, { status: 409 });
await assert.rejects(api.startAnalysis("game", true, "stale-attempt"), (error) => error.status === 409 && error.message === "Попытка уже заменена");
globalThis.fetch = async () => Response.json({ detail: "Сохранённого объяснения нет" }, { status: 404 });
await assert.rejects(api.streamMoveCommentary("game", 0), (error) => error.status === 404);
console.log("PASS: SSE whitespace/CRLF/chunks/UTF-8, cp/mate/legacy scores, explicit side/recovery requests, read-only missing commentary.");
