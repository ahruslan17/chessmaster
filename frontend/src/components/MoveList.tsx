import type { MoveAnalysisRead } from "../api/types";
import { CLASSIFICATION_META } from "../classification";

interface MoveListProps {
  moves: MoveAnalysisRead[];
  currentMoveIndex: number;
  onSelectMove: (index: number) => void;
}

export function MoveList({
  moves,
  currentMoveIndex,
  onSelectMove,
}: MoveListProps) {
  const byNumber = new Map<number, MoveAnalysisRead[]>();
  for (const m of moves) {
    const list = byNumber.get(m.move_number) ?? [];
    list.push(m);
    byNumber.set(m.move_number, list);
  }

  const moveNumbers = Array.from(byNumber.keys()).sort((a, b) => a - b);
  const grouped = moveNumbers.map((n) => {
    const list = byNumber.get(n)!;
    const white = list.find((m) => m.color === "white");
    const black = list.find((m) => m.color === "black");
    return { moveNumber: n, white, black };
  });

  // positionIndex = moveIndex + 1 (position after that move)
  const positionIndexByMoveId = new Map(moves.map((m, idx) => [m.id, idx + 1]));
  const getPositionIndex = (m: MoveAnalysisRead) => positionIndexByMoveId.get(m.id) ?? 0;

  return (
    <div className="overflow-hidden rounded-lg border border-stone-300 bg-stone-200/50 dark:border-stone-600 dark:bg-chess-light/30">
      <div className="border-b border-stone-300 px-3 py-2 dark:border-stone-600">
        <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-300">Moves</h3>
      </div>

      <div className="grid grid-cols-[3rem_1fr_1fr] border-b border-stone-300 bg-stone-200/90 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-stone-500 dark:border-stone-600 dark:bg-chess-light/60 dark:text-stone-300">
        <span>#</span>
        <span>White</span>
        <span>Black</span>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {grouped.map(({ moveNumber, white, black }, idx) => (
          <div
            key={moveNumber}
            className={`grid grid-cols-[3rem_1fr_1fr] items-center gap-2 px-3 py-2 ${
              idx % 2 === 0
                ? "bg-stone-100/70 dark:bg-chess-dark/20"
                : "bg-stone-200/40 dark:bg-chess-light/10"
            }`}
          >
            <span className="text-sm font-medium text-stone-500 dark:text-stone-400">
              {moveNumber}.
            </span>

            {white ? (
              <MoveButton
                move={white}
                isActive={getPositionIndex(white) === currentMoveIndex}
                onClick={() => onSelectMove(getPositionIndex(white))}
              />
            ) : (
              <EmptyCell />
            )}

            {black ? (
              <MoveButton
                move={black}
                isActive={getPositionIndex(black) === currentMoveIndex}
                onClick={() => onSelectMove(getPositionIndex(black))}
              />
            ) : (
              <EmptyCell />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyCell() {
  return (
    <div className="rounded border border-dashed border-stone-400/70 px-2 py-1.5 text-center text-xs text-stone-400 dark:border-stone-500/40 dark:text-stone-500">
      -
    </div>
  );
}

function MoveButton({
  move,
  isActive,
  onClick,
}: {
  move: MoveAnalysisRead;
  isActive: boolean;
  onClick: () => void;
}) {
  const meta = move.classification
    ? CLASSIFICATION_META[move.classification as keyof typeof CLASSIFICATION_META]
    : null;
  const cls = meta?.colorClass ?? "";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded border px-2 py-1.5 text-left text-sm font-medium transition ${
        isActive
          ? "ring-2 ring-chess-highlight ring-offset-2 ring-offset-stone-100 dark:ring-offset-chess-dark"
          : "hover:brightness-110"
      } ${cls}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5">
          {meta && (
            <img
              src={meta.iconSrc}
              alt={meta.iconTitle}
              title={meta.iconTitle}
              className="h-3.5 w-3.5"
            />
          )}
          <span>{move.move_san}</span>
        </span>
        <span className="text-[10px] opacity-80">
          {move.centipawn_loss != null ? `${Math.round(move.centipawn_loss)} cp` : ""}
        </span>
      </div>
    </button>
  );
}
