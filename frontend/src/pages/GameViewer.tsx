import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Chess } from "chess.js";
import { CLASSIFICATION_META } from "../classification";
import { useGame } from "../hooks/useGames";
import { useAnalysis, useAnalysisStatus } from "../hooks/useAnalysis";
import { AnalysisLegend } from "../components/AnalysisLegend";
import { ChessBoard } from "../components/ChessBoard";
import { MoveList } from "../components/MoveList";
import { CommentaryPanel } from "../components/CommentaryPanel";
import { EvalBar } from "../components/EvalBar";
import { ScoringHelpDrawer } from "../components/ScoringHelpDrawer";
import * as api from "../api/client";
import type { MoveAnalysisRead, PlayerColor, ReviewMoment } from "../api/types";

const INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function GameViewer() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const [currentMoveIndex, setCurrentMoveIndex] = useState(0);
  const [autoplay, setAutoplay] = useState(false);
  const [showScoringHelp, setShowScoringHelp] = useState(false);
  const [chosenColor, setChosenColor] = useState<PlayerColor>();
  const [rotated, setRotated] = useState(false);
  const [requestBusy, setRequestBusy] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [variation, setVariation] = useState<{ title: string; positions: string[]; moves: string[]; index: number } | null>(null);
  const [variationError, setVariationError] = useState<string | null>(null);
  const [boardElement, setBoardElement] = useState<HTMLDivElement | null>(null);
  const [boardSize, setBoardSize] = useState(240);

  const { data: game, isLoading: gameLoading, error: gameError } = useGame(gameId ?? null);
  const playerColor = chosenColor ?? (game?.player_color === "white" || game?.player_color === "black" ? game.player_color : undefined);
  const { data: status, error: statusError, refetch: refetchStatus } = useAnalysisStatus(gameId ?? null, playerColor);
  const engineStatus = status?.engine_status ?? status?.status;
  const { data: analysis, error: analysisError, isLoading: analysisLoading, refetch: refetchAnalysis } = useAnalysis(
    gameId ?? null,
    engineStatus === "queued" || engineStatus === "in_progress" || status?.review_status === "queued" || status?.review_status === "in_progress",
    playerColor
  );

  const replay = useMemo(() => buildReplay(game?.pgn_text), [game?.pgn_text]);
  const verifiedReview = playerColor && analysis?.score_version === 1 && analysis.review?.player_color === playerColor && analysis.review.context?.version === 1
    && analysis.review.context.player_color === playerColor ? analysis.review : null;
  const moves = replay.moves.map((move, index) => {
    const analyzed = analysis?.moves[index];
    return analyzed ? { ...analyzed, llm_comment: verifiedReview ? analyzed.llm_comment : null } : move;
  });
  const currentMove = currentMoveIndex > 0 ? moves[currentMoveIndex - 1] ?? null : null;
  const currentFen = variation?.positions[variation.index] ?? replay.positions[currentMoveIndex] ?? INITIAL_FEN;
  const lastMoveSquares = variation ? null : replay.squares[currentMoveIndex - 1] ?? null;
  const score = variation ? null : currentMoveIndex > 0 ? currentMove?.score_after : analysis?.moves[0]?.score_before;
  const baseOrientation = game?.player_color === "black" ? "black" : "white";
  const orientation = rotated ? (baseOrientation === "white" ? "black" : "white") : baseOrientation;
  const maxIndex = replay.moves.length;
  const currentBadge = currentMove?.classification
    ? CLASSIFICATION_META[currentMove.classification as keyof typeof CLASSIFICATION_META]
    : null;
  const missingAnalysis = analysisError instanceof api.ApiError && analysisError.status === 404;
  const analysisReadError = missingAnalysis ? null : analysisError;

  // Status transitions only refresh read-only data; never start generation here.
  useEffect(() => {
    void refetchAnalysis();
  }, [status?.engine_status, status?.status, status?.review_status, refetchAnalysis]);

  useEffect(() => {
    if (!boardElement) return;
    const update = () => setBoardSize(Math.max(1, Math.min(620, Math.floor(boardElement.getBoundingClientRect().width) - 8)));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(boardElement);
    return () => observer.disconnect();
  }, [boardElement]);

  // Autoplay
  useEffect(() => {
    if (!autoplay || currentMoveIndex >= maxIndex) {
      setAutoplay(false);
      return;
    }
    const t = setTimeout(() => setCurrentMoveIndex((index) => index + 1), 800);
    return () => clearTimeout(t);
  }, [autoplay, currentMoveIndex, maxIndex]);

  const goToMove = useCallback((index: number) => {
    setVariation(null);
    setVariationError(null);
    setAutoplay(false);
    setCurrentMoveIndex(Math.max(0, Math.min(index, maxIndex)));
  }, [maxIndex]);

  const start = async (kind: "engine" | "review", recover = false) => {
    if (!gameId || (kind === "review" && !playerColor)) return;
    if (recover && !analysis) return;
    const expectedAttemptId = kind === "engine" ? analysis?.engine_attempt_id
      : analysis?.review && analysis.review.player_color === playerColor ? analysis.review.attempt_id : null;
    if (recover && !window.confirm("Восстановить задачу вручную? Подтвердите, что прежний worker остановлен. Активная попытка будет заменена; её поздние результаты не применятся. Сохранённые результаты останутся доступны.")) return;
    setRequestBusy(true);
    setRequestError(null);
    try {
      if (kind === "engine") await api.startAnalysis(gameId, recover, expectedAttemptId);
      else await api.startExplanations(gameId, playerColor!, recover, expectedAttemptId);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Не удалось запустить задачу");
    } finally {
      await Promise.all([refetchStatus(), refetchAnalysis()]);
      setRequestBusy(false);
    }
  };

  const playLine = (moment: ReviewMoment, kind: "played" | "best") => {
    setAutoplay(false);
    setVariationError(null);
    try {
      const line = readLine(kind === "played" ? moment.played_line : moment.best_line);
      if (line.length === 0) throw new Error("Проверенная линия недоступна.");
      // Both verified lines start before the selected move, including the first SAN.
      const chess = new Chess(moment.fen_before);
      const positions = [chess.fen()];
      for (const san of line.slice(0, 8)) {
        chess.move(san);
        positions.push(chess.fen());
      }
      setCurrentMoveIndex(moment.move_index + 1);
      setVariation({ title: kind === "played" ? "Сыгранный вариант" : "Лучший вариант", positions, moves: line.slice(0, 8), index: 0 });
    } catch {
      setVariationError("Линия недоступна или не соответствует позиции. Ходы партии не изменены.");
    }
  };

  if (gameLoading || !gameId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-stone-600 dark:text-stone-500">Загрузка партии...</p>
      </div>
    );
  }

  if (gameError || !game) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-400">Партия не найдена</p>
        <button
          onClick={() => navigate("/")}
          className="mt-4 text-chess-highlight hover:underline dark:text-chess-highlight"
        >
          Назад к партиям
        </button>
      </div>
    );
  }

  const actualEngineStatus = engineStatus ?? analysis?.engine_status ?? "pending";
  const engineBusy = actualEngineStatus === "queued" || actualEngineStatus === "in_progress";
  const reviewStatus = status?.review_status ?? verifiedReview?.status;
  const reviewBusy = reviewStatus === "queued" || reviewStatus === "in_progress";
  const moments = verifiedReview?.context?.moments ?? [];
  const selectedMoment = moments.find((moment) => moment.move_index === currentMoveIndex - 1);

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          onClick={() => navigate("/")}
          className="text-stone-600 transition hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
        >
          {"← Назад к партиям"}
        </button>
        <div className="min-w-0 break-words sm:flex-1 sm:text-center">
          <h1 className="text-lg font-semibold text-stone-800 dark:text-stone-100">
            {game.white_player} vs {game.black_player}
          </h1>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {game.result} {game.opening_name ? ` - ${game.opening_name}` : ""}
          </p>
        </div>
      </div>

      <section className="space-y-3 rounded-lg border border-stone-300 bg-stone-200/50 p-4 text-sm dark:border-stone-600 dark:bg-chess-light/30">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="review-color">Разбор моей стороны</label>
          <select id="review-color" value={playerColor ?? ""} disabled={requestBusy} onChange={(event) => { setChosenColor(event.target.value as PlayerColor); setRequestError(null); setVariation(null); }} className="rounded border border-stone-400 bg-white px-3 py-2 dark:border-stone-600 dark:bg-chess-dark">
            <option value="" disabled>Выберите сторону</option>
            <option value="white">Белые</option>
            <option value="black">Чёрные</option>
          </select>
          <NavButton onClick={() => setRotated((value) => !value)}>↻ Повернуть доску</NavButton>
        </div>
        {!playerColor && <p>Выберите сторону для учебного разбора. Просмотр ходов доступен без выбора.</p>}
        <p className="text-stone-600 dark:text-stone-300">Смена стороны и поворот доски ничего не запускают. Движок и объяснения — отдельные действия.</p>
        <div role="status" aria-live="polite" className="space-y-1">
          <p>Движок: {statusLabel(actualEngineStatus)}{(status?.progress_total ?? analysis?.progress_total ?? 0) > 0 ? ` · ${status?.progress_current ?? analysis?.progress_current ?? 0}/${status?.progress_total ?? analysis?.progress_total}` : ""}</p>
          <p>Объяснения: {playerColor ? statusLabel(reviewStatus ?? "pending") : "сторона не выбрана"}</p>
          {analysisLoading && <p>Загрузка сохранённого анализа…</p>}
          {actualEngineStatus === "done" && !verifiedReview && <p>Доступен только движок. Старые или непроверенные тексты скрыты; создайте объяснения выбранной стороны.</p>}
          {reviewStatus === "partial" && <p>Объяснения готовы частично. Сохранённые комментарии доступны; можно повторить только объяснения.</p>}
          {verifiedReview?.error === "context_empty" && <p>Движок не выделил полезных собственных ошибок для объяснения. Моменты не добавляются искусственно; учебный текст не генерировался.</p>}
          {!!Object.keys(verifiedReview?.comments ?? {}).length && <p>Структура и линии проверены автоматически. Смысл объяснений ещё требует экспертной оценки.</p>}
          {analysis && actualEngineStatus === "done" && analysis.score_version !== 1 && <p>Старый анализ: знак и мат по прежним оценкам не восстанавливаются. Для проверенных оценок повторите движок.</p>}
          {(status?.engine_error || analysis?.engine_error) && <p className="break-words text-red-400">Движок: {status?.engine_error ?? analysis?.engine_error}. Сохранённые ходы не удалены.</p>}
          {(status?.review_error || verifiedReview?.error) && (status?.review_error ?? verifiedReview?.error) !== "context_empty" && <p className="break-words text-red-400">Объяснения: {status?.review_error ?? verifiedReview?.error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <NavButton onClick={() => void start("engine")} disabled={requestBusy || engineBusy || reviewBusy || (actualEngineStatus === "done" && analysis?.score_version === 1) || !!statusError || !!analysisReadError}>{actualEngineStatus === "done" && analysis?.score_version === 1 ? "Данные движка сохранены" : actualEngineStatus === "failed" || actualEngineStatus === "done" ? "Повторить движок" : "Запустить движок"}</NavButton>
          <NavButton onClick={() => void start("review")} disabled={requestBusy || engineBusy || reviewBusy || verifiedReview?.status === "done" || actualEngineStatus !== "done" || !playerColor || !!statusError || !!analysisReadError}>{verifiedReview?.status === "done" ? "Разбор стороны сохранён" : verifiedReview ? "Дополнить объяснения" : "Разобрать эту сторону / Создать объяснения"}</NavButton>
          <NavButton onClick={() => { void refetchStatus(); void refetchAnalysis(); }} disabled={requestBusy}>Обновить статус</NavButton>
        </div>
        {(engineBusy || reviewBusy) && <div className="space-y-2">
          <p>Если worker остановлен, восстановите задачу вручную. Время ожидания само по себе не означает сбой.</p>
          {(status?.heartbeat_at ?? analysis?.heartbeat_at) && <p className="break-words">Последний heartbeat движка: {status?.heartbeat_at ?? analysis?.heartbeat_at}</p>}
          {engineBusy && <NavButton disabled={requestBusy || !analysis || !!analysisReadError} onClick={() => void start("engine", true)}>Worker остановлен: восстановить движок…</NavButton>}
          {reviewBusy && <NavButton disabled={requestBusy || !playerColor || analysis?.review?.player_color !== playerColor || !!analysisReadError} onClick={() => void start("review", true)}>Worker остановлен: восстановить объяснения…</NavButton>}
        </div>}
        {requestBusy && <p role="status">Отправка запроса…</p>}
        {(requestError || statusError || analysisReadError) && <p role="alert" className="break-words text-red-400">{requestError ?? statusError?.message ?? analysisReadError?.message} Используйте «Обновить статус» для повторной загрузки. Повтор не удаляет сохранённые результаты.</p>}
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 items-start gap-2">
          <EvalBar
            score={score}
            orientation={orientation}
            height={boardSize}
          />

          <div ref={setBoardElement} className="flex min-w-0 flex-1 flex-col gap-3">
            <ChessBoard
              position={currentFen}
              orientation={orientation}
              lastMove={lastMoveSquares}
              moveBadge={
                currentBadge && lastMoveSquares
                  ? {
                      square: lastMoveSquares.to,
                      iconSrc: currentBadge.iconSrc,
                      title: currentBadge.iconTitle,
                    }
                  : null
              }
              boardWidth={boardSize}
            />

            {variation && <div className="space-y-2 rounded border border-stone-400 p-3 text-sm dark:border-stone-600">
              <p>{variation.title} · {variation.index}/{variation.moves.length}</p>
              <p className="break-words">{variation.moves.join(" ")}</p>
              <div className="flex flex-wrap gap-2">
                <NavButton disabled={variation.index === 0} onClick={() => setVariation({ ...variation, index: variation.index - 1 })}>← Вариант</NavButton>
                <NavButton disabled={variation.index >= variation.moves.length} onClick={() => setVariation({ ...variation, index: variation.index + 1 })}>Вариант →</NavButton>
                <NavButton onClick={() => setVariation(null)}>Вернуться к партии</NavButton>
              </div>
              <p>Оценка линии не показана: оценка партии относится к другой позиции.</p>
            </div>}
            {variationError && <p role="alert" className="text-sm text-red-400">{variationError}</p>}
            <div className="flex flex-wrap gap-2">
              <NavButton onClick={() => goToMove(0)} disabled={currentMoveIndex === 0}>
                ⏮ В начало
              </NavButton>
              <NavButton onClick={() => goToMove(currentMoveIndex - 1)} disabled={currentMoveIndex === 0}>
                ← Назад
              </NavButton>
              <NavButton onClick={() => goToMove(currentMoveIndex + 1)} disabled={currentMoveIndex >= maxIndex}>
                Вперед →
              </NavButton>
              <NavButton onClick={() => goToMove(maxIndex)} disabled={currentMoveIndex >= maxIndex}>
                В конец ⏭
              </NavButton>
              <NavButton
                onClick={() => setAutoplay((value) => !value)}
                disabled={currentMoveIndex >= maxIndex || !!variation}
                active={autoplay}
              >
                {autoplay ? "⏸ Пауза" : "▶ Автоплей"}
              </NavButton>
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {moves.length > 0 && (
            <MoveList
              moves={moves}
              currentMoveIndex={currentMoveIndex}
              onSelectMove={goToMove}
            />
          )}

          <section className="space-y-3 rounded-lg border border-stone-300 p-4 text-sm dark:border-stone-600">
            <h3 className="font-semibold text-stone-600 dark:text-stone-400">Учебные моменты выбранной стороны</h3>
            {moments.length ? <div className="flex flex-wrap gap-2">{moments.map((moment) => <NavButton key={moment.move_index} active={currentMoveIndex === moment.move_index + 1} onClick={() => goToMove(moment.move_index + 1)}>{moment.move_number}{moment.color === "white" ? "." : "…"} {moment.move_san}</NavButton>)}</div> : <p>Проверенных учебных моментов пока нет. Не каждый ход требует объяснения.</p>}
            {selectedMoment && <div className="flex flex-wrap gap-2">
              <NavButton onClick={() => playLine(selectedMoment, "played")} disabled={readLine(selectedMoment.played_line).length === 0}>Сыгранный вариант</NavButton>
              <NavButton onClick={() => playLine(selectedMoment, "best")} disabled={readLine(selectedMoment.best_line).length === 0}>Лучший вариант</NavButton>
            </div>}
          </section>
          <CommentaryPanel move={currentMove} summary={verifiedReview?.summary} />
          {!!verifiedReview?.recommendations.length && <section className="rounded-lg border border-stone-300 p-4 text-sm dark:border-stone-600"><h3 className="mb-2 font-semibold">Что тренировать</h3><ul className="list-inside list-disc space-y-2">{verifiedReview.recommendations.map((text, index) => <li key={index}>{text}</li>)}</ul></section>}

          <AnalysisLegend onOpenHelp={() => setShowScoringHelp(true)} />
        </div>
      </div>

      <ScoringHelpDrawer
        isOpen={showScoringHelp}
        onClose={() => setShowScoringHelp(false)}
      />
    </div>
  );
}

function NavButton({
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
      className={`min-h-10 rounded px-2 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "bg-chess-highlight text-stone-100"
          : "bg-stone-300 text-stone-700 hover:bg-stone-400 disabled:hover:bg-stone-300 dark:bg-stone-600/50 dark:text-stone-300 dark:hover:bg-stone-600 dark:disabled:hover:bg-stone-600/50"
      }`}
    >
      {children}
    </button>
  );
}

function buildReplay(pgnText?: string) {
  try {
    const chess = new Chess();
    chess.loadPgn(pgnText ?? "");
    const history = chess.history({ verbose: true });
    const moves: MoveAnalysisRead[] = history.map((move, index) => ({
      id: `pgn-${index}`, move_number: Number(move.before.split(" ")[5]), color: move.color === "w" ? "white" : "black",
      move_san: move.san, best_move_san: null, eval_before: null, eval_after: null,
      centipawn_loss: null, classification: null, top_moves: null, continuation_lines: null, llm_comment: null,
    }));
    return { moves, positions: [history[0]?.before ?? chess.fen(), ...history.map((move) => move.after)], squares: history.map((move) => ({ from: move.from, to: move.to })) };
  } catch {
    return { moves: [], positions: [INITIAL_FEN], squares: [] };
  }
}

function statusLabel(status: string) {
  return ({ pending: "не запущен", queued: "в очереди", in_progress: "выполняется", done: "готов", partial: "частично готов", failed: "ошибка" } as Record<string, string>)[status] ?? status;
}

function readLine(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.filter((move): move is string => typeof move === "string");
  if (raw && typeof raw === "object") {
    const line = raw as Record<string, unknown>;
    const moves = line.moves_san ?? line.pv_san ?? line.san ?? line.moves;
    if (Array.isArray(moves)) return moves.filter((move): move is string => typeof move === "string");
  }
  return [];
}
