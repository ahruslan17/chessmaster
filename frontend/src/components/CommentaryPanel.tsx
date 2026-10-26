import type { MoveAnalysisRead, MoveExplanation } from "../api/types";
import { CLASSIFICATION_META } from "../classification";

interface CommentaryPanelProps {
  move: MoveAnalysisRead | null;
  summary?: string | null;
  loading?: boolean;
  generating?: boolean;
  onPlayLine?: (kind: "played" | "best") => void;
  activeVariationKind?: "played" | "best";
  playedLineAvailable?: boolean;
  bestLineAvailable?: boolean;
}

export function CommentaryPanel({
  move,
  summary,
  loading = false,
  generating = false,
  onPlayLine,
  activeVariationKind,
  playedLineAvailable = false,
  bestLineAvailable = false,
}: CommentaryPanelProps) {
  // Read-only projection. Selecting a move never requests or generates commentary.
  const comment = move?.llm_comment ?? null;
  const detailed = move?.commentary?.version === 2 ? move.commentary : null;
  const sameMove = !!move?.best_move_san && move.move_san === move.best_move_san;
  const classificationMeta = move?.classification
    ? CLASSIFICATION_META[move.classification as keyof typeof CLASSIFICATION_META]
    : null;

  const notation = (san: string) => `${move!.move_number}${move!.color === "black" ? "…" : "."} ${san}`;
  const lineButton = (kind: "played" | "best", available: boolean) => available && onPlayLine ? (
    <div className="mt-3 space-y-1.5">
    <button
      type="button"
      onClick={() => onPlayLine(kind)}
      aria-pressed={activeVariationKind === kind}
      className={`min-h-10 rounded px-3 py-2 text-sm font-medium ${activeVariationKind === kind ? "bg-chess-highlight text-white" : "bg-stone-200 text-stone-800 hover:bg-stone-300 dark:bg-stone-700 dark:text-stone-100 dark:hover:bg-stone-600"}`}
    >
      Показать вариант после <span className="font-mono">{kind === "played" ? move?.move_san : move?.best_move_san}</span> на доске
    </button>
    <p className="text-xs leading-relaxed text-stone-600 dark:text-stone-300">Возможное продолжение по расчёту движка, не следующие ходы партии.</p>
    </div>
  ) : null;

  return (
    <div className="min-w-0 [overflow-wrap:anywhere]">
      <h2 className="mb-4 text-base font-semibold text-stone-800 dark:text-stone-100">{move ? !detailed && comment ? "Сохранённый комментарий" : "Разбор хода" : summary ? "Итог партии" : "Разбор партии"}</h2>
      <div className="space-y-5 text-sm text-stone-700 dark:text-stone-200">
        {move ? (
          <>
            <section aria-label="Сыграно в партии">
              <h3 className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-semibold text-stone-800 dark:text-stone-100">
                <span>Сыграно в партии</span>
                <span className="font-mono text-base">{notation(move.move_san)}</span>
              </h3>
              <div className="mb-3 flex flex-wrap gap-2">
                {classificationMeta && !(move.is_theory && move.classification === "theory") && (
                  <span className="rounded border border-stone-400 px-2 py-0.5 text-xs text-stone-700 dark:border-stone-500 dark:text-stone-200">
                    {move.classification === "best" && !sameMove ? "Один из лучших" : classificationMeta.label}
                  </span>
                )}
                {move.is_theory && (
                  <span className={`rounded border px-2 py-0.5 text-xs ${CLASSIFICATION_META.theory.colorClass}`}>Из дебютной базы</span>
                )}
              </div>
              {sameMove && <p className="mb-3 text-stone-600 dark:text-stone-300">Совпадает с рекомендацией движка</p>}
              {detailed ? <Explanation explanation={detailed.played} /> : comment ? (
                <p className="max-w-prose whitespace-pre-wrap leading-relaxed">{comment}</p>
              ) : (
                <p className="text-stone-600 dark:text-stone-300">{loading ? "Загружаем объяснение…" : generating ? "Объяснение этого хода ещё готовится." : "Для этого хода пока нет объяснения."}</p>
              )}
              {playedLineAvailable ? lineButton("played", true) : sameMove ? lineButton("best", bestLineAvailable) : null}
            </section>
            {!sameMove && move.best_move_san && <section aria-label="Рекомендация движка" className="border-t border-stone-300 pt-4 dark:border-stone-600">
              <h3 className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-semibold text-stone-800 dark:text-stone-100">
                <span>Рекомендация движка</span>
                <span className="font-mono text-base">{notation(move.best_move_san)}</span>
              </h3>
              {detailed?.alternative ? <Explanation explanation={detailed.alternative} /> : (
                <p className="text-stone-600 dark:text-stone-300">{loading ? "Загружаем объяснение…" : generating ? "Готовим объяснение рекомендации…" : "Объяснение рекомендации не получено: разбор ещё не завершён."}</p>
              )}
              {lineButton("best", bestLineAvailable)}
            </section>}
            {!move.best_move_san && detailed && <p className="text-stone-600 dark:text-stone-300">Для этой позиции нет сохранённой рекомендации движка.</p>}
            {!sameMove && move.best_move_san && detailed?.comparison?.trim() && (
              <section aria-label="Сравнение ходов" className="border-t border-stone-300 pt-4 dark:border-stone-600">
                <h3 className="mb-2 font-semibold text-stone-800 dark:text-stone-100">Сравнение ходов</h3>
                <p className="max-w-prose whitespace-pre-wrap leading-relaxed">{detailed.comparison}</p>
              </section>
            )}
          </>
        ) : summary ? (
          <p className="leading-relaxed">{summary}</p>
        ) : (
          <p className="text-stone-600 dark:text-stone-300">Выберите ход в списке или нажмите «Вперёд», чтобы увидеть его идею.</p>
        )}
      </div>
    </div>
  );
}

function Explanation({ explanation }: { explanation: MoveExplanation }) {
  const fields: [keyof MoveExplanation, string][] = [
    ["pros", "Плюсы"],
    ["cons", "Риски"],
    ["tactics", "Тактика"],
    ["plan", "Дальнейший план"],
    ["opponent_reply", "Ответ соперника"],
    ["missed_opportunity", "Упущенная возможность"],
  ];

  return (
    <dl className="max-w-prose space-y-3 leading-relaxed">
      <div>
        <dt className="mb-0.5 font-semibold text-stone-800 dark:text-stone-100">Идея хода</dt>
        <dd className="whitespace-pre-wrap text-base text-stone-800 dark:text-stone-100">{explanation.idea}</dd>
      </div>
      {fields.map(([field, label]) => explanation[field]?.trim() ? (
        <div key={field}>
          <dt className="mb-0.5 font-semibold text-stone-800 dark:text-stone-100">{label}</dt>
          <dd className="whitespace-pre-wrap">{explanation[field]}</dd>
        </div>
      ) : null)}
    </dl>
  );
}
