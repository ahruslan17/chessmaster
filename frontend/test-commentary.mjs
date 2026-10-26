// Compile CommentaryPanel.tsx with --module commonjs --jsx react-jsx, then pass
// the output directory. NODE_PATH must include existing frontend/node_modules.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const compiled = resolve(process.argv[2]);
const require = createRequire(resolve(compiled, "package.json"));
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { CommentaryPanel } = require(resolve(compiled, "components/CommentaryPanel.js"));
const move = {
  id: "move", move_number: 8, color: "white", move_san: "cxd5", best_move_san: "Rc1",
  classification: "best", llm_comment: "Старый общий абзац.",
  commentary: {
    version: 2,
    played: { idea: "Идея сыгранного хода.", pros: "Польза хода.", tactics: null, cons: "  " },
    alternative: { idea: "Идея рекомендации.", plan: "План рекомендации." },
    comparison: "Отличие ходов.",
  },
};
const render = (current) => renderToStaticMarkup(React.createElement(CommentaryPanel, {
  move: current, playedLineAvailable: true, bestLineAvailable: true, onPlayLine() {},
}));

const detailed = render(move);
assert.match(detailed, /Сыграно в партии/);
assert.match(detailed, /Рекомендация движка/);
assert.ok(detailed.indexOf("Идея сыгранного хода.") < detailed.indexOf("Рекомендация движка"));
assert.ok(detailed.indexOf("Идея рекомендации.") > detailed.indexOf("Рекомендация движка"));
assert.match(detailed, /Один из лучших/);
assert.match(detailed, /Сравнение ходов/);
assert.match(detailed, /Показать вариант после <span class="font-mono">cxd5<\/span> на доске/);
assert.match(detailed, /Показать вариант после <span class="font-mono">Rc1<\/span> на доске/);
assert.match(detailed, /Возможное продолжение по расчёту движка, не следующие ходы партии/);
assert.doesNotMatch(detailed, /Показать последствия хода|Показать линию рекомендации/);
assert.doesNotMatch(detailed, /Старый общий абзац|Тактика|Риски/);

const matching = render({ ...move, best_move_san: "cxd5" });
assert.match(matching, /Совпадает с рекомендацией движка/);
assert.doesNotMatch(matching, /aria-label="Рекомендация движка"|Сравнение ходов|Идея рекомендации/);
assert.equal((matching.match(/<button/g) ?? []).length, 1);

const legacy = render({ ...move, commentary: null });
assert.match(legacy, /Сохранённый комментарий/);
assert.match(legacy, /Старый общий абзац\./);
assert.doesNotMatch(legacy, /Идея сыгранного хода|Плюсы|Дальнейший план/);

const missing = render({ ...move, commentary: null, llm_comment: null });
assert.match(missing, /Для этого хода пока нет объяснения/);
assert.match(missing, /Объяснение рекомендации не получено: разбор ещё не завершён/);
const generating = renderToStaticMarkup(React.createElement(CommentaryPanel, {
  move: { ...move, commentary: null }, generating: true,
}));
assert.match(generating, /Готовим объяснение рекомендации/);
const noRecommendation = render({ ...move, best_move_san: null });
assert.doesNotMatch(noRecommendation, /aria-label="Рекомендация движка"|Идея рекомендации|Сравнение ходов/);
console.log("PASS: separated commentary, optional sections, matching move, legacy and missing explanations.");
