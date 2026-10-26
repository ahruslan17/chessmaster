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
  const [variation, setVariation] = useState<{ kind: "played" | "best"; title: string; positions: string[]; moves: string[]; index: number; startNumber: number; startsBlack: boolean } | null>(null);
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
  const variationMove = useMemo(() => {
    if (!variation || variation.index === 0) return null;
    const board = new Chess(variation.positions[variation.index - 1]);
    const move = board.move(variation.moves[variation.index - 1]);
    return { from: move.from, to: move.to };
  }, [variation]);
  const lastMoveSquares = variation ? variationMove ?? null : replay.squares[currentMoveIndex - 1] ?? null;
  const score = variation ? null : currentMoveIndex > 0 ? currentMove?.score_after : analysis?.moves[0]?.score_before;
  const baseOrientation = game?.player_color === "black" ? "black" : "white";
  const orientation = rotated ? (baseOrientation === "white" ? "black" : "white") : baseOrientation;
  const maxIndex = replay.moves.length;
  const currentBadge = currentMove?.is_theory
    ? CLASSIFICATION_META.theory
    : currentMove?.classification
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
    const index = variation?.index ?? currentMoveIndex;
    const end = variation?.moves.length ?? maxIndex;
    if (!autoplay || index >= end) {
      setAutoplay(false);
      return;
    }
    const t = setTimeout(() => {
      if (variation) setVariation((line) => line ? { ...line, index: line.index + 1 } : null);
      else setCurrentMoveIndex((value) => value + 1);
    }, 800);
    return () => clearTimeout(t);
  }, [autoplay, currentMoveIndex, maxIndex, variation]);

  const goToMove = useCallback((index: number) => {
    setVariation(null);
    setVariationError(null);
    setAutoplay(false);
    setCurrentMoveIndex(Math.max(0, Math.min(index, maxIndex)));
  }, [maxIndex]);

  const navigateBoard = (index: number) => {
    setAutoplay(false);
    if (variation) setVariation({ ...variation, index: Math.max(0, Math.min(index, variation.moves.length)) });
    else goToMove(index);
  };

  const returnToGame = () => {
    setAutoplay(false);
    setVariation(null);
  };

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
      else await api.startExplanations(gameId, recover ? analysis?.review?.owner_color ?? playerColor! : playerColor!, recover, expectedAttemptId);
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
      setVariation({ kind, title: kind === "played" ? "Продолжение после хода в партии" : "Лучшее продолжение", positions, moves: line.slice(0, 8), index: 1, startNumber: moment.move_number, startsBlack: moment.color === "black" });
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
  const fullCommentary = verifiedReview?.context?.commentary_scope === "all_moves";
  const commentaryComplete = fullCommentary && verifiedReview?.status === "done";
  const commentCount = Object.keys(verifiedReview?.comments ?? {}).length;
  const reviewBusy = reviewStatus === "queued" || reviewStatus === "in_progress";
  const moments = verifiedReview?.context?.moments ?? [];
  const selectedMoment = moments.find((moment) => moment.move_index === currentMoveIndex - 1);
  const boardIndex = variation?.index ?? currentMoveIndex;
  const boardMaxIndex = variation?.moves.length ?? maxIndex;

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
            {game.result} {game.eco_code} {game.opening_name ? ` - ${game.opening_name}` : ""}
          </p>
        </div>
      </div>

      <section className="space-y-3 rounded-lg border border-stone-300 bg-stone-200/50 p-4 text-sm dark:border-stone-600 dark:bg-chess-light/30">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="review-color">Сторона для учебных моментов</label>
          <select id="review-color" value={playerColor ?? ""} disabled={requestBusy} onChange={(event) => { setChosenColor(event.target.value as PlayerColor); setRequestError(null); setVariation(null); setAutoplay(false); }} className="rounded border border-stone-400 bg-white px-3 py-2 dark:border-stone-600 dark:bg-chess-dark">
            <option value="" disabled>Выберите сторону</option>
            <option value="white">Белые</option>
            <option value="black">Чёрные</option>
          </select>
          <NavButton onClick={() => setRotated((value) => !value)}>↻ Повернуть доску</NavButton>
        </div>
        {!playerColor && <p>Выберите сторону для учебного разбора. Просмотр ходов доступен без выбора.</p>}
        <p className="text-stone-600 dark:text-stone-300">Полный разбор комментирует каждый ход обеих сторон. Выбор стороны меняет подборку учебных моментов, но не запускает генерацию. Поворот доски независим.</p>
        <div role="status" aria-live="polite" className="space-y-1">
          <p>Движок: {statusLabel(actualEngineStatus)}{(status?.progress_total ?? analysis?.progress_total ?? 0) > 0 ? ` · ${status?.progress_current ?? analysis?.progress_current ?? 0}/${status?.progress_total ?? analysis?.progress_total}` : ""}</p>
          <p>Комментарии: {playerColor ? statusLabel(fullCommentary ? reviewStatus ?? "pending" : "pending") : "выберите сторону для учебных моментов"}{fullCommentary ? ` · ${commentCount}/${moves.length} полуходов` : ""}</p>
          {analysisLoading && <p>Загрузка сохранённого анализа…</p>}
          {actualEngineStatus === "done" && !fullCommentary && <p>Полный походовый разбор ещё не создан. Нажмите «Комментировать все ходы». Сохранённые комментарии останутся доступны.</p>}
          {reviewStatus === "partial" && fullCommentary && <p>Разбор готов частично. Дополнение обработает только ходы без комментариев; движок повторно не запускается.</p>}
          {!!Object.keys(verifiedReview?.comments ?? {}).length && <p>Структура и линии проверены автоматически. Смысл объяснений ещё требует экспертной оценки.</p>}
          {analysis && actualEngineStatus === "done" && analysis.score_version !== 1 && <p>Старый анализ: знак и мат по прежним оценкам не восстанавливаются. Для проверенных оценок повторите движок.</p>}
          {(status?.engine_error || analysis?.engine_error) && <p className="break-words text-red-400">Движок: {status?.engine_error ?? analysis?.engine_error}. Сохранённые ходы не удалены.</p>}
          {(status?.review_error || verifiedReview?.error) && (status?.review_error ?? verifiedReview?.error) !== "context_empty" && <p className="break-words text-red-400">Объяснения: {status?.review_error ?? verifiedReview?.error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <NavButton onClick={() => void start("engine")} disabled={requestBusy || engineBusy || reviewBusy || (actualEngineStatus === "done" && analysis?.score_version === 1) || !!statusError || !!analysisReadError}>{actualEngineStatus === "done" && analysis?.score_version === 1 ? "Данные движка сохранены" : actualEngineStatus === "failed" || actualEngineStatus === "done" ? "Повторить движок" : "Запустить движок"}</NavButton>
          <NavButton onClick={() => void start("review")} disabled={requestBusy || engineBusy || reviewBusy || commentaryComplete || actualEngineStatus !== "done" || !playerColor || !!statusError || !!analysisReadError}>{commentaryComplete ? "Все ходы прокомментированы" : fullCommentary ? "Дополнить комментарии" : "Комментировать все ходы"}</NavButton>
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
                !variation && currentBadge && lastMoveSquares
                  ? {
                      square: lastMoveSquares.to,
                      iconSrc: currentBadge.iconSrc,
                      title: currentBadge.iconTitle,
                    }
                  : null
              }
              boardWidth={boardSize}
            />

            {variation && <div aria-label="Линия движка" className="space-y-2 rounded border border-chess-highlight p-3 text-sm">
              <p role="status"><strong>Линия движка</strong> · {variation.title} · {variation.index === 0 ? "Позиция до хода" : `Полуход ${variation.index} из ${variation.moves.length}`}</p>
              <p className="text-stone-600 dark:text-stone-300">Возможное продолжение, не ходы из партии. Стрелки под доской листают эту линию.</p>
              <div className="flex flex-wrap gap-1" aria-label="Ходы линии движка">
                <NavButton active={variation.index === 0} onClick={() => navigateBoard(0)}>До хода</NavButton>
                {variation.moves.map((san, index) => {
                  const ply = index + (variation.startsBlack ? 1 : 0);
                  const label = `${variation.startNumber + Math.floor(ply / 2)}${ply % 2 ? "…" : "."} ${san}`;
                  return <NavButton key={index} active={variation.index === index + 1} onClick={() => navigateBoard(index + 1)}>{label}</NavButton>;
                })}
              </div>
              <NavButton onClick={returnToGame}>Вернуться к ходу {currentMove?.move_number}{currentMove?.color === "black" ? "…" : "."} {currentMove?.move_san} в партии</NavButton>
              <p className="text-stone-600 dark:text-stone-300">Оценка и комментарий партии не относятся к позиции внутри линии.</p>
            </div>}
            {variationError && <p role="alert" className="text-sm text-red-400">{variationError}</p>}
            <div className="flex flex-wrap gap-2">
              <NavButton onClick={() => navigateBoard(0)} disabled={boardIndex === 0}>
                ⏮ В начало
              </NavButton>
              <NavButton onClick={() => navigateBoard(boardIndex - 1)} disabled={boardIndex === 0}>
                ← Назад
              </NavButton>
              <NavButton onClick={() => navigateBoard(boardIndex + 1)} disabled={boardIndex >= boardMaxIndex}>
                Вперед →
              </NavButton>
              <NavButton onClick={() => navigateBoard(boardMaxIndex)} disabled={boardIndex >= boardMaxIndex}>
                В конец ⏭
              </NavButton>
              <NavButton
                onClick={() => setAutoplay((value) => !value)}
                disabled={boardIndex >= boardMaxIndex}
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
            {moments.length ? <div className="flex flex-wrap gap-2">{moments.map((moment) => <NavButton key={moment.move_index} active={currentMoveIndex === moment.move_index + 1} onClick={() => goToMove(moment.move_index + 1)}>{moment.move_number}{moment.color === "white" ? "." : "…"} {moment.move_san}</NavButton>)}</div> : <p>{fullCommentary ? "Для выбранной стороны движок не выделил ошибок. Комментарии ко всем ходам доступны независимо от этой подборки." : "Подборка появится при запуске полного разбора. Она не ограничивает комментарии к остальным ходам."}</p>}
            {selectedMoment && <div className="flex flex-wrap gap-2">
              <NavButton active={variation?.kind === "played"} onClick={() => playLine(selectedMoment, "played")} disabled={readLine(selectedMoment.played_line).length === 0}>После {selectedMoment.move_san} в партии</NavButton>
              <NavButton active={variation?.kind === "best"} onClick={() => playLine(selectedMoment, "best")} disabled={readLine(selectedMoment.best_line).length === 0}>Лучше: {selectedMoment.best_move_san}</NavButton>
            </div>}
          </section>
          {variation && <p role="note" className="text-sm text-stone-600 dark:text-stone-300">Комментарий ниже относится к ходу {currentMove?.move_number}{currentMove?.color === "black" ? "…" : "."} {currentMove?.move_san} из партии, а не к открытой линии движка.</p>}
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
      aria-pressed={active}
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
