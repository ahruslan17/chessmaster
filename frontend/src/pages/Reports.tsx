import { useState } from "react";
import { useReports, useCreateReport } from "../hooks/useReports";

export function Reports() {
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [periodType, setPeriodType] = useState("weekly");

  const { data: reports = [], isLoading } = useReports();
  const createReport = useCreateReport();

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!periodStart || !periodEnd) return;
    try {
      await createReport.mutateAsync({
        period_start: periodStart,
        period_end: periodEnd,
        period_type: periodType,
      });
      setPeriodStart("");
      setPeriodEnd("");
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-stone-800 dark:text-stone-100">Period Reports</h1>

      <form onSubmit={handleCreate} className="flex flex-wrap gap-4 rounded-lg border border-stone-300 bg-stone-200/50 p-6 dark:border-stone-600 dark:bg-chess-light/30">
        <div>
          <label className="mb-1 block text-sm text-stone-600 dark:text-stone-500">Start date</label>
          <input
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            className="rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-stone-600 dark:text-stone-500">End date</label>
          <input
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            className="rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-stone-600 dark:text-stone-500">Period type</label>
          <select
            value={periodType}
            onChange={(e) => setPeriodType(e.target.value)}
            className="rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          >
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={createReport.isPending || !periodStart || !periodEnd}
            className="rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:opacity-50"
          >
            {createReport.isPending ? "Creating..." : "Generate Report"}
          </button>
        </div>
      </form>

      {isLoading ? (
        <p className="py-8 text-center text-stone-500">Loading reports...</p>
      ) : reports.length === 0 ? (
        <div className="rounded-lg border border-stone-300 bg-stone-200/50 py-12 text-center dark:border-stone-600 dark:bg-chess-light/20">
          <p className="text-stone-600 dark:text-stone-500">No reports yet. Generate one for a date range.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {reports.map((r) => (
            <div
              key={r.id}
              className="rounded-lg border border-stone-300 bg-stone-200/50 p-6 dark:border-stone-600 dark:bg-chess-light/30"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-stone-800 dark:text-stone-200">
                    {new Date(r.period_start).toLocaleDateString()} –{" "}
                    {new Date(r.period_end).toLocaleDateString()}
                  </p>
                  <p className="text-sm text-stone-600 dark:text-stone-500">
                    {r.period_type} • {Array.isArray(r.game_ids) ? r.game_ids.length : 0} games
                  </p>
                </div>
                <p className="text-sm text-stone-600 dark:text-stone-500">
                  {new Date(r.created_at).toLocaleString()}
                </p>
              </div>
              {r.recommendations && (
                <div className="mt-4 rounded border border-stone-300 bg-stone-100 p-4 dark:border-stone-600/50 dark:bg-chess-dark/50">
                  <p className="text-sm font-medium text-stone-600 dark:text-stone-400">Recommendations</p>
                  <p className="mt-2 text-sm text-stone-700 whitespace-pre-wrap dark:text-stone-300">{r.recommendations}</p>
                </div>
              )}
              {Array.isArray(r.weakness_patterns) && r.weakness_patterns.length > 0 && (
                <div className="mt-4 rounded border border-amber-300 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
                  <p className="text-sm font-medium text-amber-700 dark:text-amber-400">Weakness patterns</p>
                  <ul className="mt-2 space-y-2">
                    {r.weakness_patterns.map((p, i) => (
                      <li key={i} className="text-sm text-stone-700 dark:text-stone-300">
                        <strong className="text-amber-600 dark:text-amber-300">{p.pattern}</strong>
                        {p.frequency && (
                          <span className="text-stone-500"> ({p.frequency})</span>
                        )}
                        <p className="mt-0.5 text-stone-600 dark:text-stone-400">{p.description}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {Array.isArray(r.strength_patterns) && r.strength_patterns.length > 0 && (
                <div className="mt-4 rounded border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/30">
                  <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Strength patterns</p>
                  <ul className="mt-2 space-y-2">
                    {r.strength_patterns.map((p, i) => (
                      <li key={i} className="text-sm text-stone-700 dark:text-stone-300">
                        <strong className="text-emerald-600 dark:text-emerald-300">{p.pattern}</strong>
                        {p.frequency && (
                          <span className="text-stone-500"> ({p.frequency})</span>
                        )}
                        <p className="mt-0.5 text-stone-600 dark:text-stone-400">{p.description}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
