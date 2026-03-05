interface EvalBarProps {
  evalCentipawns: number; // from white's perspective, positive = white better
  orientation?: "white" | "black";
  height?: number;
}

function clampEval(cp: number): number {
  const capped = Math.min(Math.max(cp, -500), 500);
  return capped;
}

function toPercent(cp: number, orientation: "white" | "black"): number {
  const clamped = clampEval(cp);
  // Map -500..500 to 0..100. 0 = black winning, 100 = white winning
  const pct = ((clamped + 500) / 1000) * 100;
  return orientation === "black" ? 100 - pct : pct;
}

export function EvalBar({
  evalCentipawns,
  orientation = "white",
  height = 120,
}: EvalBarProps) {
  const pct = toPercent(evalCentipawns, orientation);
  const display =
    Math.abs(evalCentipawns) >= 1000
      ? `M${Math.abs(Math.round(evalCentipawns / 1000))}`
      : (evalCentipawns / 100).toFixed(1);

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative w-5 overflow-hidden rounded border border-stone-400 bg-stone-300 dark:border-stone-600 dark:bg-stone-800"
        style={{ height }}
      >
        <div
          className="absolute bottom-0 left-0 right-0 bg-stone-700 transition-all duration-200 dark:bg-stone-100"
          style={{ height: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-stone-500 dark:text-stone-400">{display}</span>
    </div>
  );
}
