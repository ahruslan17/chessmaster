import { CLASSIFICATION_META, CLASSIFICATION_ORDER } from "../classification";

interface AnalysisLegendProps {
  onOpenHelp: () => void;
}

export function AnalysisLegend({ onOpenHelp }: AnalysisLegendProps) {
  return (
    <div className="rounded-lg border border-stone-300 bg-stone-200/40 px-3 py-2.5 dark:border-stone-600 dark:bg-chess-light/20">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
          Legend
        </h3>
        <button
          type="button"
          onClick={onOpenHelp}
          className="rounded border border-stone-400 px-2 py-0.5 text-[11px] text-stone-600 transition hover:bg-stone-300 dark:border-stone-500/50 dark:text-stone-300 dark:hover:bg-stone-600/50"
        >
          Scoring
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {CLASSIFICATION_ORDER.map((key) => {
          const meta = CLASSIFICATION_META[key];
          return (
            <span
              key={`legend-${key}`}
              className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium ${meta.colorClass}`}
            >
              <img
                src={meta.iconSrc}
                alt={meta.iconTitle}
                title={meta.iconTitle}
                className="h-3 w-3"
              />
              <span>{meta.label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
