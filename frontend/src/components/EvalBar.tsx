import type { EngineScore } from "../api/types";
import { presentScore } from "../engineScore";

interface EvalBarProps {
  score?: EngineScore | null;
  orientation?: "white" | "black";
  height?: number;
}

export function EvalBar({
  score,
  orientation = "white",
  height = 120,
}: EvalBarProps) {
  const { label: display, whitePercent: pct, description } = presentScore(score);
  const whiteFillStyle =
    orientation === "black"
      ? { height: `${pct}%`, top: 0 }
      : { height: `${pct}%`, bottom: 0 };

  return (
    <div className="flex w-10 shrink-0 flex-col items-center gap-1" role="img" aria-label={description} title={description}>
      <div
        className="relative w-5 overflow-hidden rounded border border-stone-500/80 bg-black"
        style={{ height }}
      >
        <div
          className="absolute left-0 right-0 bg-white motion-safe:transition-all motion-safe:duration-200"
          style={whiteFillStyle}
        />
      </div>
      <span className="text-xs text-stone-500 dark:text-stone-400">{display}</span>
    </div>
  );
}
