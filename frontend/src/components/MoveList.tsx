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
  // Group moves by move number: 1. e4 e5 2. Nf3 Nc6
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

  // moveIndex = 0-based index in moves array; positionIndex = moveIndex + 1 (position after that move)
  const getMoveIndex = (m: MoveAnalysisRead) =>
    moves.findIndex((x) => x.id === m.id);
  const toPositionIndex = (moveIndex: number) => moveIndex + 1;

  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
      <h3 className="mb-3 text-sm font-semibold text-stone-600 dark:text-stone-400">Moves</h3>
      <div className="flex flex-wrap gap-2">
        {grouped.map(({ moveNumber, white, black }) => (
          <span key={moveNumber} className="flex items-center gap-1">
            <span className="text-stone-500 dark:text-stone-400">{moveNumber}.</span>
            {white && (
              <MoveButton
                move={white}
                isActive={toPositionIndex(getMoveIndex(white)) === currentMoveIndex}
                onClick={() => onSelectMove(toPositionIndex(getMoveIndex(white)))}
              />
            )}
            {black && (
              <MoveButton
                move={black}
                isActive={toPositionIndex(getMoveIndex(black)) === currentMoveIndex}
                onClick={() => onSelectMove(toPositionIndex(getMoveIndex(black)))}
              />
            )}
          </span>
        ))}
      </div>
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
  const cls = move.classification
    ? CLASSIFICATION_META[move.classification as keyof typeof CLASSIFICATION_META]?.colorClass ?? ""
    : "";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-2 py-1 text-sm font-medium transition ${
        isActive
          ? "ring-2 ring-chess-highlight ring-offset-2 ring-offset-stone-100 dark:ring-offset-chess-dark"
          : "hover:bg-stone-300 dark:hover:bg-stone-600/50"
      } ${cls}`}
    >
      {move.move_san}
    </button>
  );
}
