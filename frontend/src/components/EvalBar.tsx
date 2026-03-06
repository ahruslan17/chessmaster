interface EvalBarProps {
  evalCentipawns: number; // from white's perspective, positive = white better
  orientation?: "white" | "black";
  height?: number;
}

function clampEval(cp: number): number {
  const capped = Math.min(Math.max(cp, -500), 500);
  return capped;
}

function toPercent(cp: number): number {
  const clamped = clampEval(cp);
  // Map -500..500 to 0..100. 0 = black winning, 100 = white winning
  return ((clamped + 500) / 1000) * 100;
}

export function EvalBar({
  evalCentipawns,
  orientation = "white",
  height = 120,
}: EvalBarProps) {
  const pct = toPercent(evalCentipawns);
  const display =
    Math.abs(evalCentipawns) >= 1000
      ? `M${Math.abs(Math.round(evalCentipawns / 1000))}`
      : (evalCentipawns / 100).toFixed(1);
  const whiteFillStyle =
    orientation === "black"
      ? { height: `${pct}%`, top: 0 }
      : { height: `${pct}%`, bottom: 0 };

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative w-5 overflow-hidden rounded border border-stone-500/80 bg-black"
        style={{ height }}
      >
        <div
          className="absolute left-0 right-0 bg-white transition-all duration-200"
          style={whiteFillStyle}
        />
      </div>
      <span className="text-xs text-stone-500 dark:text-stone-400">{display}</span>
    </div>
  );
}
