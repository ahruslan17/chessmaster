import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import type {
  GameNoteListItem,
  ReportPattern,
  ReportRead,
} from "../api/types";
import { useAnalysis } from "../hooks/useAnalysis";
import { useGames } from "../hooks/useGames";
import { useGameNote, useGameNotes, useUpsertGameNote } from "../hooks/useNotes";
import { useCreateReport, useReports } from "../hooks/useReports";

type DiaryTab = "matches" | "periods" | "notes";
type PeriodType = "daily" | "weekly" | "monthly";

type FeedbackSections = {
  pluses: string[];
  minuses: string[];
  focusPoints: string[];
  tasks: string[];
};

type DeltaMetric = {
  current: number | string;
  previous: number | string;
  delta: number | string;
  delta_percent?: number | null;
};

export function Diary() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<DiaryTab>("matches");
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteOrigin, setNoteOrigin] = useState("");
  const [periodType, setPeriodType] = useState<PeriodType>("weekly");
  const [reportFilter, setReportFilter] = useState<"all" | PeriodType>("all");
  const [periodStart, setPeriodStart] = useState(() => getPeriodRange("weekly").start);
  const [periodEnd, setPeriodEnd] = useState(() => getPeriodRange("weekly").end);

  const { data: games = [], isLoading: gamesLoading } = useGames({ limit: 200 });
  const { data: analysis, isLoading: analysisLoading } = useAnalysis(selectedGameId, false);
  const { data: note, isLoading: noteLoading } = useGameNote(selectedGameId);
  const { data: reports = [], isLoading: reportsLoading } = useReports(
    reportFilter === "all" ? {} : { period_type: reportFilter }
  );
  const { data: gameNotes = [], isLoading: gameNotesLoading } = useGameNotes({
    limit: 300,
  });

  const createReport = useCreateReport();
  const upsertNote = useUpsertGameNote();

  useEffect(() => {
    if (selectedGameId) {
      return;
    }
    if (games.length > 0) {
      setSelectedGameId(games[0].id);
    }
  }, [games, selectedGameId]);

  useEffect(() => {
    const content = note?.content ?? "";
    setNoteDraft(content);
    setNoteOrigin(content);
  }, [note?.id, note?.content]);

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;
  const noteDirty = noteDraft.trim() !== noteOrigin.trim();
  const verifiedReview = analysis?.score_version === 1 && analysis.review?.context?.version === 1
    && analysis.review.player_color === selectedGame?.player_color ? analysis.review : null;
  const gameFeedback = normalizeFeedback(verifiedReview ? { focus_points: verifiedReview.recommendations } : null);

  const handleSaveNote = async () => {
    if (!selectedGameId) {
      return;
    }
    const saved = await upsertNote.mutateAsync({
      gameId: selectedGameId,
      content: noteDraft.trim(),
    });
    setNoteOrigin(saved.content ?? "");
  };

  const handleCreateReport = async (event: FormEvent) => {
    event.preventDefault();
    if (!periodStart || !periodEnd) {
      return;
    }
    await createReport.mutateAsync({
      period_start: periodStart,
      period_end: periodEnd,
      period_type: periodType,
    });
  };

  const applyPreset = (preset: PeriodType) => {
    const range = getPeriodRange(preset);
    setPeriodType(preset);
    setPeriodStart(range.start);
    setPeriodEnd(range.end);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-stone-800 dark:text-stone-100">Дневник</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            Послематчевый фидбек, отчёты по периодам и личные заметки в одном месте.
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-stone-300 bg-stone-200/70 p-1 dark:border-stone-600 dark:bg-chess-light/30">
          <TabButton
            active={tab === "matches"}
            onClick={() => setTab("matches")}
            label="Партии"
          />
          <TabButton
            active={tab === "periods"}
            onClick={() => setTab("periods")}
            label="Периоды"
          />
          <TabButton
            active={tab === "notes"}
            onClick={() => setTab("notes")}
            label="Заметки"
          />
        </div>
      </div>

      {tab === "matches" && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <section className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
                Выбор партии
              </h2>
              <span className="text-xs text-stone-500 dark:text-stone-400">{games.length} шт.</span>
            </div>
            <div className="max-h-[44rem] space-y-2 overflow-y-auto pr-1">
              {gamesLoading ? (
                <p className="py-6 text-center text-sm text-stone-500">Загрузка партий...</p>
              ) : games.length === 0 ? (
                <p className="py-6 text-center text-sm text-stone-500">
                  Пока нет партий. Загрузите PGN в разделе «Партии».
                </p>
              ) : (
                games.map((game) => (
                  <button
                    key={game.id}
                    type="button"
                    onClick={() => setSelectedGameId(game.id)}
                    className={`w-full rounded-md border px-3 py-2 text-left transition ${
                      selectedGameId === game.id
                        ? "border-chess-highlight bg-chess-highlight/15"
                        : "border-stone-300 bg-stone-100/60 hover:bg-stone-100 dark:border-stone-600 dark:bg-chess-dark/30 dark:hover:bg-chess-dark/50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium text-stone-800 dark:text-stone-100">
                        {game.white_player} vs {game.black_player}
                      </p>
                      <span className="shrink-0 rounded border border-stone-400/80 bg-stone-100 px-2 py-0.5 text-xs font-semibold text-stone-700 dark:border-stone-500 dark:bg-chess-dark/70 dark:text-stone-200">
                        {formatDate(game.played_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                      {game.result} • {game.opening_name ?? "Без дебюта"}
                    </p>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="space-y-4">
            {selectedGame ? (
              <>
                <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-stone-800 dark:text-stone-100">
                        {selectedGame.white_player} vs {selectedGame.black_player}
                      </h2>
                      <p className="text-sm text-stone-500 dark:text-stone-400">
                        {selectedGame.result} • {selectedGame.opening_name ?? "Без дебюта"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate(`/games/${selectedGame.id}`)}
                      className="rounded border border-stone-400 px-3 py-2 text-sm text-stone-700 transition hover:bg-stone-100 dark:border-stone-500 dark:text-stone-300 dark:hover:bg-stone-700/40"
                    >
                      Открыть партию
                    </button>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <FeedbackCard title="Плюсы" items={gameFeedback.pluses} tone="good" />
                  <FeedbackCard title="Минусы" items={gameFeedback.minuses} tone="warn" />
                  <FeedbackCard
                    title="Фокус на ближайшие партии"
                    items={gameFeedback.focusPoints}
                    tone="neutral"
                  />
                  <FeedbackCard title="План тренировки" items={gameFeedback.tasks} tone="accent" />
                </div>

                <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
                    Комментарий ИИ по партии
                  </h3>
                  {analysisLoading ? (
                    <p className="mt-3 text-sm text-stone-500">Загрузка анализа...</p>
                  ) : verifiedReview?.summary ? (
                    <div className="mt-3 space-y-2 text-sm text-stone-700 dark:text-stone-300">
                      <p className="whitespace-pre-wrap leading-relaxed">{verifiedReview.summary}</p>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-stone-500">
                      Проверенного разбора вашей стороны пока нет. Старые тексты скрыты; откройте партию, выберите сторону и явно запустите объяснения.
                    </p>
                  )}
                </div>

                <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
                      Мои заметки по партии
                    </h3>
                    <span className="text-xs text-stone-500 dark:text-stone-400">
                      {note?.updated_at ? `Обновлено: ${formatDateTime(note.updated_at)}` : "Черновик"}
                    </span>
                  </div>
                  <textarea
                    value={noteDraft}
                    onChange={(event) => setNoteDraft(event.target.value)}
                    rows={7}
                    placeholder="Например: где потерял нить позиции, что повторить, какие задачи решить."
                    className="mt-3 w-full resize-y rounded-md border border-stone-400 bg-white px-3 py-2 text-sm text-stone-800 placeholder-stone-500 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
                  />
                  <div className="mt-3 flex items-center justify-end">
                    <button
                      type="button"
                      onClick={handleSaveNote}
                      disabled={!selectedGameId || upsertNote.isPending || noteLoading || !noteDirty}
                      className="rounded bg-chess-highlight px-4 py-2 text-sm font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {upsertNote.isPending ? "Сохранение..." : "Сохранить заметку"}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-stone-300 bg-stone-200/40 p-8 text-center text-sm text-stone-500 dark:border-stone-600 dark:bg-chess-light/20 dark:text-stone-400">
                Выберите партию слева, чтобы посмотреть тренерский фидбек и вести заметки.
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "periods" && (
        <div className="space-y-4">
          <form
            onSubmit={handleCreateReport}
            className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30"
          >
            <div className="grid gap-4 md:grid-cols-[12rem_1fr_1fr_auto]">
              <div>
                <label className="mb-1 block text-sm text-stone-600 dark:text-stone-400">Период</label>
                <select
                  value={periodType}
                  onChange={(event) => setPeriodType(event.target.value as PeriodType)}
                  className="w-full rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
                >
                  <option value="daily">День</option>
                  <option value="weekly">Неделя</option>
                  <option value="monthly">Месяц</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm text-stone-600 dark:text-stone-400">
                  Дата начала
                </label>
                <input
                  type="date"
                  value={periodStart}
                  onChange={(event) => setPeriodStart(event.target.value)}
                  className="w-full rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-stone-600 dark:text-stone-400">Дата конца</label>
                <input
                  type="date"
                  value={periodEnd}
                  onChange={(event) => setPeriodEnd(event.target.value)}
                  className="w-full rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
                />
              </div>
              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={createReport.isPending || !periodStart || !periodEnd}
                  className="w-full rounded bg-chess-highlight px-4 py-2 text-sm font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createReport.isPending ? "Формирование..." : "Сформировать"}
                </button>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <QuickButton onClick={() => applyPreset("daily")} label="Сегодня" />
              <QuickButton onClick={() => applyPreset("weekly")} label="Последние 7 дней" />
              <QuickButton onClick={() => applyPreset("monthly")} label="Последние 30 дней" />
            </div>
          </form>

          <div className="flex items-center gap-2">
            <span className="text-sm text-stone-600 dark:text-stone-400">Фильтр:</span>
            <FilterButton
              active={reportFilter === "all"}
              label="Все"
              onClick={() => setReportFilter("all")}
            />
            <FilterButton
              active={reportFilter === "daily"}
              label="День"
              onClick={() => setReportFilter("daily")}
            />
            <FilterButton
              active={reportFilter === "weekly"}
              label="Неделя"
              onClick={() => setReportFilter("weekly")}
            />
            <FilterButton
              active={reportFilter === "monthly"}
              label="Месяц"
              onClick={() => setReportFilter("monthly")}
            />
          </div>

          {reportsLoading ? (
            <p className="py-8 text-center text-stone-500">Загрузка отчётов...</p>
          ) : reports.length === 0 ? (
            <div className="rounded-lg border border-dashed border-stone-300 bg-stone-200/40 p-8 text-center text-sm text-stone-500 dark:border-stone-600 dark:bg-chess-light/20 dark:text-stone-400">
              Пока нет отчётов по периодам.
            </div>
          ) : (
            <div className="space-y-4">
              {reports.map((report) => (
                <ReportCard key={report.id} report={report} />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "notes" && (
        <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
              Личные заметки
            </h2>
            <span className="text-xs text-stone-500 dark:text-stone-400">{gameNotes.length} записей</span>
          </div>
          {gameNotesLoading ? (
            <p className="py-8 text-center text-stone-500">Загрузка заметок...</p>
          ) : gameNotes.length === 0 ? (
            <p className="py-8 text-center text-sm text-stone-500">
              Вы пока не добавляли заметки по партиям.
            </p>
          ) : (
            <div className="space-y-3">
              {gameNotes.map((item) => (
                <NoteCard
                  key={`${item.game_id}-${item.updated_at}`}
                  item={item}
                  onOpenGame={() => navigate(`/games/${item.game_id}`)}
                  onEditInDiary={() => {
                    setSelectedGameId(item.game_id);
                    setTab("matches");
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
        active
          ? "bg-chess-highlight text-stone-100"
          : "text-stone-600 hover:bg-stone-300/80 dark:text-stone-300 dark:hover:bg-stone-700/70"
      }`}
    >
      {label}
    </button>
  );
}

function FeedbackCard({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "good" | "warn" | "neutral" | "accent";
}) {
  const toneClass =
    tone === "good"
      ? "border-emerald-300/70 bg-emerald-50/70 dark:border-emerald-900/60 dark:bg-emerald-950/20"
      : tone === "warn"
        ? "border-amber-300/70 bg-amber-50/70 dark:border-amber-900/60 dark:bg-amber-950/20"
        : tone === "accent"
          ? "border-blue-300/70 bg-blue-50/70 dark:border-blue-900/60 dark:bg-blue-950/20"
          : "border-stone-300 bg-stone-100/70 dark:border-stone-600 dark:bg-chess-dark/20";

  return (
    <div className={`rounded-lg border p-4 ${toneClass}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-600 dark:text-stone-300">
        {title}
      </h3>
      {items.length > 0 ? (
        <ul className="mt-2 space-y-1 text-sm text-stone-700 dark:text-stone-300">
          {items.map((item, index) => (
            <li key={`${title}-${index}`} className="leading-relaxed">
              • {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">Пока нет данных.</p>
      )}
    </div>
  );
}

function QuickButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-stone-400 px-3 py-1.5 text-xs font-medium text-stone-700 transition hover:bg-stone-100 dark:border-stone-500 dark:text-stone-300 dark:hover:bg-stone-700/40"
    >
      {label}
    </button>
  );
}

function FilterButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded border px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "border-chess-highlight bg-chess-highlight/15 text-stone-800 dark:text-stone-100"
          : "border-stone-400 text-stone-600 hover:bg-stone-100 dark:border-stone-500 dark:text-stone-300 dark:hover:bg-stone-700/40"
      }`}
    >
      {label}
    </button>
  );
}

function ReportCard({ report }: { report: ReportRead }) {
  const feedback = normalizeFeedback(report.coach_feedback);
  const metrics = parseDeltaMetrics(report.comparison_metrics);

  return (
    <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-stone-800 dark:text-stone-100">
            {formatDate(report.period_start)} - {formatDate(report.period_end)}
          </h3>
          <p className="text-xs uppercase tracking-wide text-stone-500 dark:text-stone-400">
            {formatPeriodType(report.period_type)} • {report.game_ids?.length ?? 0} партий
          </p>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400">{formatDateTime(report.created_at)}</p>
      </div>

      {report.comparison_summary && (
        <div className="mt-3 rounded-md border border-stone-300 bg-stone-100/70 p-3 text-sm text-stone-700 dark:border-stone-600 dark:bg-chess-dark/30 dark:text-stone-300">
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
            Сравнение с предыдущим периодом
          </p>
          <p className="mt-1 leading-relaxed">{report.comparison_summary}</p>
        </div>
      )}

      {metrics.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {metrics.map((metric) => (
            <span
              key={metric.key}
              className={`rounded border px-2 py-1 text-xs ${
                metric.delta >= 0
                  ? "border-emerald-400/70 text-emerald-700 dark:border-emerald-700 dark:text-emerald-300"
                  : "border-rose-400/70 text-rose-700 dark:border-rose-700 dark:text-rose-300"
              }`}
            >
              {metric.label}: {metric.delta >= 0 ? "+" : ""}
              {metric.delta}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <FeedbackCard title="Прогресс" items={feedback.pluses} tone="good" />
        <FeedbackCard title="Проблемы" items={feedback.minuses} tone="warn" />
      </div>

      {report.recommendations && (
        <div className="mt-4 rounded-md border border-stone-300 bg-stone-100/70 p-3 text-sm text-stone-700 dark:border-stone-600 dark:bg-chess-dark/30 dark:text-stone-300">
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
            Рекомендации
          </p>
          <p className="mt-1 whitespace-pre-wrap leading-relaxed">{report.recommendations}</p>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <PatternList title="Слабые паттерны" patterns={report.weakness_patterns} tone="warn" />
        <PatternList title="Сильные паттерны" patterns={report.strength_patterns} tone="good" />
      </div>
    </div>
  );
}

function PatternList({
  title,
  patterns,
  tone,
}: {
  title: string;
  patterns: ReportPattern[] | null;
  tone: "good" | "warn";
}) {
  const borderClass =
    tone === "good"
      ? "border-emerald-300/70 bg-emerald-50/70 dark:border-emerald-900/60 dark:bg-emerald-950/20"
      : "border-amber-300/70 bg-amber-50/70 dark:border-amber-900/60 dark:bg-amber-950/20";

  return (
    <div className={`rounded-md border p-3 ${borderClass}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-600 dark:text-stone-300">
        {title}
      </p>
      {patterns && patterns.length > 0 ? (
        <ul className="mt-2 space-y-2 text-sm text-stone-700 dark:text-stone-300">
          {patterns.map((pattern, index) => (
            <li key={`${pattern.pattern}-${index}`}>
              <p className="font-medium">{pattern.pattern}</p>
              {pattern.frequency && <p className="text-xs text-stone-500">{pattern.frequency}</p>}
              <p className="text-sm leading-relaxed">{pattern.description}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">Нет данных.</p>
      )}
    </div>
  );
}

function NoteCard({
  item,
  onOpenGame,
  onEditInDiary,
}: {
  item: GameNoteListItem;
  onOpenGame: () => void;
  onEditInDiary: () => void;
}) {
  return (
    <div className="rounded-md border border-stone-300 bg-stone-100/70 p-3 dark:border-stone-600 dark:bg-chess-dark/30">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-stone-800 dark:text-stone-100">
            {item.white_player} vs {item.black_player}
          </p>
          <p className="text-xs text-stone-500 dark:text-stone-400">
            {item.opening_name ?? "Без дебюта"} • {formatDate(item.played_at)}
          </p>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400">{formatDateTime(item.updated_at)}</p>
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-stone-700 dark:text-stone-300">
        {item.content ?? ""}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onEditInDiary}
          className="rounded border border-stone-400 px-3 py-1.5 text-xs font-medium text-stone-700 transition hover:bg-stone-100 dark:border-stone-500 dark:text-stone-300 dark:hover:bg-stone-700/40"
        >
          Открыть в дневнике
        </button>
        <button
          type="button"
          onClick={onOpenGame}
          className="rounded border border-stone-400 px-3 py-1.5 text-xs font-medium text-stone-700 transition hover:bg-stone-100 dark:border-stone-500 dark:text-stone-300 dark:hover:bg-stone-700/40"
        >
          К партии
        </button>
      </div>
    </div>
  );
}

function getPeriodRange(periodType: PeriodType): { start: string; end: string } {
  const now = new Date();
  const end = toDateInput(now);

  if (periodType === "daily") {
    return { start: end, end };
  }

  const days = periodType === "weekly" ? 6 : 29;
  const startDate = new Date(now);
  startDate.setDate(now.getDate() - days);

  return {
    start: toDateInput(startDate),
    end,
  };
}

function toDateInput(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleDateString("ru-RU");
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function formatPeriodType(value: string): string {
  if (value === "daily") {
    return "День";
  }
  if (value === "weekly") {
    return "Неделя";
  }
  if (value === "monthly") {
    return "Месяц";
  }
  return value;
}

function normalizeFeedback(raw: unknown): FeedbackSections {
  if (!raw || typeof raw !== "object") {
    return { pluses: [], minuses: [], focusPoints: [], tasks: [] };
  }
  const source = raw as Record<string, unknown>;
  return {
    pluses: normalizeStringArray(source.pluses),
    minuses: normalizeStringArray(source.minuses),
    focusPoints: normalizeStringArray(source.focus_points),
    tasks: [
      ...normalizeStringArray(source.training_tasks),
      ...normalizeStringArray(source.action_items),
    ],
  };
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter((entry) => entry.length > 0);
}

function parseDeltaMetrics(
  raw: Record<string, unknown> | null
): Array<{ key: string; label: string; delta: number }> {
  if (!raw) {
    return [];
  }

  const metrics: Array<{ key: string; label: string; delta: number }> = [];
  for (const [key, value] of Object.entries(raw)) {
    if (/accuracy|точност/i.test(key) || !isDeltaMetric(value)) {
      continue;
    }
    const numericDelta =
      typeof value.delta === "number" ? value.delta : Number.parseFloat(String(value.delta));
    if (!Number.isFinite(numericDelta)) {
      continue;
    }
    metrics.push({
      key,
      label: metricLabel(key),
      delta: Math.round(numericDelta * 10) / 10,
    });
  }

  return metrics.slice(0, 6);
}

function isDeltaMetric(value: unknown): value is DeltaMetric {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  return "current" in record && "previous" in record && "delta" in record;
}

function metricLabel(key: string): string {
  if (key === "games") {
    return "Количество партий";
  }
  if (key.endsWith("_moves")) {
    return `${key.replace("_moves", "")} ходы`;
  }
  return key;
}
