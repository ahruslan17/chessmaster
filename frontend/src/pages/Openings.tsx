import { useEffect, useState } from "react";
import { Chess } from "chess.js";
import type { OpeningRead } from "../api/types";
import { useOpenings } from "../hooks/useOpenings";
import { ChessBoard } from "../components/ChessBoard";

const INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type TimelineStep = {
  fen: string;
  lastMove: { from: string; to: string } | null;
};

export function Openings() {
  const [search, setSearch] = useState("");
  const [selectedOpening, setSelectedOpening] = useState<OpeningRead | null>(null);
  const [currentMoveIndex, setCurrentMoveIndex] = useState(0);
  const [autoplay, setAutoplay] = useState(false);

  const { data: openings = [], isLoading, error } = useOpenings({ limit: 5000 });

  const filteredOpenings = openings.filter((opening) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return `${opening.eco_code} ${opening.name}`.toLowerCase().includes(q);
  });

  const timeline = selectedOpening
    ? buildOpeningTimeline(selectedOpening.moves_san)
    : [{ fen: INITIAL_FEN, lastMove: null }];

  const maxIndex = Math.max(0, timeline.length - 1);
  const safeIndex = Math.max(0, Math.min(currentMoveIndex, maxIndex));
  const currentStep = timeline[safeIndex] ?? timeline[0];
  const boardWidth = useResponsiveBoardWidth();

  useEffect(() => {
    setCurrentMoveIndex(0);
    setAutoplay(false);
  }, [selectedOpening?.id]);

  useEffect(() => {
    if (!autoplay || safeIndex >= maxIndex) {
      setAutoplay(false);
      return;
    }
    const timeout = setTimeout(() => setCurrentMoveIndex((index) => index + 1), 700);
    return () => clearTimeout(timeout);
  }, [autoplay, safeIndex, maxIndex]);

  const movePairs = selectedOpening ? toMovePairs(selectedOpening.moves_san) : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-stone-800 dark:text-stone-100">Дебюты</h1>
        <span className="text-sm text-stone-500 dark:text-stone-400">
          Всего: {openings.length}
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        <section className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
          <label className="mb-2 block text-sm text-stone-600 dark:text-stone-400">Поиск дебюта</label>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Например: Sicilian, C50, French..."
            className="w-full rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 placeholder-stone-500 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          />

          <div className="mt-3 max-h-[34rem] overflow-y-auto space-y-1 pr-1">
            {isLoading ? (
              <p className="py-6 text-center text-sm text-stone-500">Загрузка дебютов...</p>
            ) : error ? (
              <p className="py-6 text-center text-sm text-red-400">Не удалось загрузить дебюты</p>
            ) : filteredOpenings.length === 0 ? (
              <p className="py-6 text-center text-sm text-stone-500">Ничего не найдено</p>
            ) : (
              filteredOpenings.map((opening) => {
                const isActive =
                  selectedOpening?.id === opening.id;

                return (
                  <button
                    key={opening.id}
                    type="button"
                    onClick={() => setSelectedOpening(opening)}
                    className={`w-full rounded border px-3 py-2 text-left transition ${
                      isActive
                        ? "border-chess-highlight bg-chess-highlight/15 text-stone-900 dark:text-stone-100"
                        : "border-stone-300 bg-stone-100/60 hover:bg-stone-100 dark:border-stone-600 dark:bg-chess-dark/30 dark:hover:bg-chess-dark/50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
                        {opening.eco_code}
                      </span>
                      <span className="text-xs text-stone-500 dark:text-stone-400">
                        {opening.move_count} полуходов
                      </span>
                    </div>
                    <p className="mt-1 text-sm font-medium text-stone-700 dark:text-stone-200">{opening.name}</p>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
          {selectedOpening ? (
            <div className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-stone-500 dark:text-stone-400">
                  {selectedOpening.eco_code}
                </p>
                <h2 className="text-lg font-semibold text-stone-800 dark:text-stone-100">
                  {selectedOpening.name}
                </h2>
                <p className="text-sm text-stone-500 dark:text-stone-400">
                  Ход: {safeIndex} / {maxIndex}
                </p>
              </div>

              <div className="flex justify-center">
                <ChessBoard
                  position={currentStep.fen}
                  orientation="white"
                  lastMove={currentStep.lastMove}
                  boardWidth={boardWidth}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <PlaybackButton onClick={() => setCurrentMoveIndex(0)} disabled={safeIndex === 0}>
                  ⏮ В начало
                </PlaybackButton>
                <PlaybackButton onClick={() => setCurrentMoveIndex((index) => Math.max(0, index - 1))} disabled={safeIndex === 0}>
                  ← Назад
                </PlaybackButton>
                <PlaybackButton onClick={() => setCurrentMoveIndex((index) => Math.min(maxIndex, index + 1))} disabled={safeIndex >= maxIndex}>
                  Вперед →
                </PlaybackButton>
                <PlaybackButton onClick={() => setCurrentMoveIndex(maxIndex)} disabled={safeIndex >= maxIndex}>
                  В конец ⏭
                </PlaybackButton>
                <PlaybackButton
                  onClick={() => setAutoplay((value) => !value)}
                  disabled={safeIndex >= maxIndex}
                  active={autoplay}
                >
                  {autoplay ? "⏸ Пауза" : "▶ Автоплей"}
                </PlaybackButton>
              </div>

              <div className="rounded border border-stone-300 bg-stone-100/70 p-3 text-sm dark:border-stone-600 dark:bg-chess-dark/30">
                <p className="mb-2 text-xs uppercase tracking-wide text-stone-500 dark:text-stone-400">
                  Линия дебюта
                </p>
                <div className="space-y-1 text-stone-700 dark:text-stone-300">
                  {movePairs.map((pair) => (
                    <p key={pair}>{pair}</p>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex min-h-[20rem] items-center justify-center rounded border border-dashed border-stone-300 bg-stone-100/60 p-6 text-center text-sm text-stone-500 dark:border-stone-600 dark:bg-chess-dark/20 dark:text-stone-400">
              Выберите дебют из списка слева, чтобы открыть доску и проиграть линию по ходам.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function PlaybackButton({
  children,
  onClick,
  disabled,
  active,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "bg-chess-highlight text-stone-100"
          : "bg-stone-300 text-stone-700 hover:bg-stone-400 disabled:hover:bg-stone-300 dark:bg-stone-600/50 dark:text-stone-300 dark:hover:bg-stone-600 dark:disabled:hover:bg-stone-600/50"
      }`}
    >
      {children}
    </button>
  );
}

function buildOpeningTimeline(movesSan: string[]): TimelineStep[] {
  const steps: TimelineStep[] = [{ fen: INITIAL_FEN, lastMove: null }];
  const chess = new Chess();

  for (const san of movesSan) {
    try {
      const played = chess.move(san);
      if (!played) break;
      steps.push({
        fen: chess.fen(),
        lastMove: { from: played.from, to: played.to },
      });
    } catch {
      break;
    }
  }

  return steps;
}

function toMovePairs(movesSan: string[]): string[] {
  const pairs: string[] = [];
  for (let i = 0; i < movesSan.length; i += 2) {
    const moveNumber = Math.floor(i / 2) + 1;
    const white = movesSan[i] ?? "";
    const black = movesSan[i + 1] ?? "";
    pairs.push(black ? `${moveNumber}. ${white} ${black}` : `${moveNumber}. ${white}`);
  }
  return pairs;
}

function useResponsiveBoardWidth(): number {
  const getBoardWidth = () => {
    if (typeof window === "undefined") return 520;
    if (window.innerWidth < 640) return Math.max(280, Math.min(380, window.innerWidth - 48));
    if (window.innerWidth < 1024) return Math.max(320, Math.min(460, window.innerWidth - 80));
    return 520;
  };

  const [boardWidth, setBoardWidth] = useState(getBoardWidth);

  useEffect(() => {
    const onResize = () => setBoardWidth(getBoardWidth());
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return boardWidth;
}
