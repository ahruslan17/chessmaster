import { CLASSIFICATION_META, CLASSIFICATION_ORDER } from "../classification";

interface AnalysisLegendProps {
  onOpenHelp: () => void;
}

export function AnalysisLegend({ onOpenHelp }: AnalysisLegendProps) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold text-stone-700 dark:text-stone-200">Обозначения</h2>
        <button
          type="button"
          onClick={onOpenHelp}
          className="min-h-10 rounded px-2 text-sm text-stone-700 transition hover:bg-stone-200 dark:text-stone-200 dark:hover:bg-stone-700"
        >
          Как читать оценку
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
                 alt=""
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
