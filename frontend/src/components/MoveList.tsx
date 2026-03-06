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
  for (const move of moves) {
    const list = byNumber.get(move.move_number) ?? [];
    list.push(move);
    byNumber.set(move.move_number, list);
  }

  const moveNumbers = Array.from(byNumber.keys()).sort((a, b) => a - b);
  const grouped = moveNumbers.map((moveNumber) => {
    const list = byNumber.get(moveNumber)!;
    const white = list.find((move) => move.color === "white");
    const black = list.find((move) => move.color === "black");
    return { moveNumber, white, black };
  });

  const positionIndexByMoveId = new Map(moves.map((move, index) => [move.id, index + 1]));
  const getPositionIndex = (move: MoveAnalysisRead) => positionIndexByMoveId.get(move.id) ?? 0;

  return (
    <div className="overflow-hidden rounded-lg border border-stone-300 bg-stone-200/50 dark:border-stone-600 dark:bg-chess-light/30">
      <div className="flex items-center justify-between border-b border-stone-300 px-3 py-2 dark:border-stone-600">
        <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-300">Ходы</h3>
        <span className="text-xs text-stone-500 dark:text-stone-400">{moves.length} полуходов</span>
      </div>

      <div className="max-h-72 overflow-y-auto px-2.5 py-2.5">
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4">
          {grouped.map(({ moveNumber, white, black }) => (
            <div
              key={moveNumber}
              className="inline-flex items-center gap-1 rounded-md border border-stone-300/70 bg-stone-100/60 px-1.5 py-0.5 dark:border-stone-600/50 dark:bg-chess-dark/20"
            >
              <span className="min-w-5 text-right text-xs font-medium text-stone-500 dark:text-stone-400">
                {moveNumber}.
              </span>

              {white && (
                <MoveChip
                  move={white}
                  isActive={getPositionIndex(white) === currentMoveIndex}
                  onClick={() => onSelectMove(getPositionIndex(white))}
                />
              )}

              {black && (
                <MoveChip
                  move={black}
                  isActive={getPositionIndex(black) === currentMoveIndex}
                  onClick={() => onSelectMove(getPositionIndex(black))}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MoveChip({
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
  const colorClass = meta?.colorClass ?? "bg-stone-300/60 text-stone-700 border-stone-400/60";
  const cp = move.centipawn_loss != null ? `${Math.round(move.centipawn_loss)} cp` : null;

  return (
    <button
      type="button"
      onClick={onClick}
      title={cp ? `${move.move_san}  -  ${cp}` : move.move_san}
      className={`rounded-md border px-2 py-0.5 text-sm font-semibold tracking-tight transition ${
        isActive
          ? "ring-2 ring-chess-highlight ring-offset-1 ring-offset-stone-100 dark:ring-offset-chess-dark"
          : "hover:brightness-110"
      } ${colorClass}`}
    >
      {move.move_san}
    </button>
  );
}

