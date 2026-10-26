import { useEffect, useRef } from "react";
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
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = listRef.current;
    const selected = list?.querySelector<HTMLButtonElement>('[aria-current="step"]');
    if (!list || !selected) return;
    const bounds = list.getBoundingClientRect();
    const chip = selected.getBoundingClientRect();
    if (chip.top < bounds.top) list.scrollTop -= bounds.top - chip.top + 8;
    else if (chip.bottom > bounds.bottom) list.scrollTop += chip.bottom - bounds.bottom + 8;
  }, [currentMoveIndex, moves]);
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
        <h2 className="text-sm font-semibold text-stone-800 dark:text-stone-100">Ходы партии</h2>
      </div>

      <div ref={listRef} className="max-h-60 overflow-y-auto px-2.5 py-2.5">
        <div className="grid gap-1.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr))]">
          {grouped.map(({ moveNumber, white, black }) => (
            <div
              key={moveNumber}
              className="inline-flex w-full break-inside-avoid flex-wrap items-center gap-1 px-1 py-0.5"
            >
              <span className="min-w-5 text-right font-mono text-xs font-medium text-stone-600 dark:text-stone-300">
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
  const quality = move.classification === "best" && move.best_move_san && move.best_move_san !== move.move_san
    ? "Один из лучших" : meta?.label;
  const label = [`Ход ${move.move_number}`, move.color === "white" ? "белые" : "чёрные", move.move_san, quality, move.is_theory ? "Из дебютной базы" : null].filter(Boolean).join(" · ");
  const icon = move.is_theory ? CLASSIFICATION_META.theory : meta;

  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-current={isActive ? "step" : undefined}
      className={`inline-flex min-h-10 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1 font-mono text-sm font-medium transition ${
        isActive
          ? "border-chess-highlight bg-chess-highlight text-white"
          : "border-transparent text-stone-800 hover:bg-stone-300 dark:text-stone-100 dark:hover:bg-stone-700"
      }`}
    >
      {move.move_san}
      {icon && <img src={icon.iconSrc} alt="" aria-hidden="true" className="h-3.5 w-3.5" />}
    </button>
  );
}
