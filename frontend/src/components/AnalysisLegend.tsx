import { CLASSIFICATION_META, CLASSIFICATION_ORDER } from "../classification";

interface AnalysisLegendProps {
  onOpenHelp: () => void;
}

export function AnalysisLegend({ onOpenHelp }: AnalysisLegendProps) {
  return (
    <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400">Legend</h3>
        <button
          type="button"
          onClick={onOpenHelp}
          className="rounded border border-stone-400 px-2 py-1 text-xs text-stone-600 transition hover:bg-stone-300 dark:border-stone-500/50 dark:text-stone-300 dark:hover:bg-stone-600/50"
        >
          How scoring works
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">Color meaning</p>
          <div className="flex flex-wrap gap-2">
            {CLASSIFICATION_ORDER.map((key) => {
              const meta = CLASSIFICATION_META[key];
              return (
                <span
                  key={`color-${key}`}
                  className={`rounded border px-2 py-1 text-xs font-medium ${meta.colorClass}`}
                >
                  {meta.label}
                </span>
              );
            })}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">Icon meaning</p>
          <div className="grid grid-cols-2 gap-2">
            {CLASSIFICATION_ORDER.map((key) => {
              const meta = CLASSIFICATION_META[key];
              return (
                <div
                  key={`icon-${key}`}
                  className="flex items-center gap-2 rounded border border-stone-300/80 bg-stone-100/80 px-2 py-1 text-xs text-stone-600 dark:border-stone-500/40 dark:bg-chess-dark/40 dark:text-stone-300"
                >
                  <img
                    src={meta.iconSrc}
                    alt={meta.iconTitle}
                    title={meta.iconTitle}
                    className="h-4 w-4"
                  />
                  <span>{meta.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
