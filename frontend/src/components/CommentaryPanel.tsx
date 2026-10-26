import type { MoveAnalysisRead } from "../api/types";
import { CLASSIFICATION_META } from "../classification";

interface CommentaryPanelProps {
  move: MoveAnalysisRead | null;
  summary?: string | null;
}

export function CommentaryPanel({
  move,
  summary,
}: CommentaryPanelProps) {
  // Read-only projection. Selecting a move never requests or generates commentary.
  const comment = move?.llm_comment ?? null;
  const classificationMeta = move?.classification
    ? CLASSIFICATION_META[move.classification as keyof typeof CLASSIFICATION_META]
    : null;

  return (
    <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
      <h3 className="mb-3 text-sm font-semibold text-stone-600 dark:text-stone-400">Комментарии</h3>
      <div className="space-y-3 break-words text-sm text-stone-700 dark:text-stone-300">
        {move ? (
          <>
            <div className="flex flex-wrap gap-2">
              <span className="rounded bg-stone-300 px-2 py-0.5 dark:bg-stone-600/50">
                {move.move_san}
              </span>
              {move.best_move_san &&
                move.move_san !== move.best_move_san &&
                move.classification !== "theory" && (
                  <span className="text-stone-500">
                    Лучший: {move.best_move_san}
                  </span>
                )}
              {classificationMeta && (
                <span className="rounded border border-stone-400 px-2 py-0.5 text-stone-600 dark:border-stone-500/50 dark:text-stone-400">
                  {classificationMeta.label}
                </span>
              )}
              {move.is_theory && (
                <span className={`rounded border px-2 py-0.5 ${CLASSIFICATION_META.theory.colorClass}`}>
                  Теория: ход из дебютной базы
                </span>
              )}
            </div>
            {comment ? (
              <p className="whitespace-pre-wrap leading-relaxed">{comment}</p>
            ) : (
              <p className="italic text-stone-500">Для этого хода комментарий отсутствует.</p>
            )}
          </>
        ) : summary ? (
          <p className="leading-relaxed">{summary}</p>
        ) : (
          <p className="italic text-stone-500">Выберите ход, чтобы посмотреть комментарий.</p>
        )}
      </div>
    </div>
  );
}
