import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
import type { MoveAnalysisRead, PlayerColor } from "../api/types";

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
  const variationContextRef = useRef<HTMLHeadingElement>(null);
  const variationTriggerRef = useRef<HTMLElement | null>(null);
  const boardControlRef = useRef<HTMLButtonElement>(null);
  const focusVariationRef = useRef(false);
  const restoreVariationFocusRef = useRef(false);

  const { data: game, isLoading: gameLoading, error: gameError } = useGame(gameId ?? null);
  const playerColor = chosenColor ?? (game?.player_color === "white" || game?.player_color === "black" ? game.player_color : undefined);
  const { data: status, error: statusError, isPending: statusLoading, refetch: refetchStatus } = useAnalysisStatus(gameId ?? null, playerColor);
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
    return analyzed ? { ...analyzed, llm_comment: verifiedReview ? analyzed.llm_comment : null, commentary: verifiedReview ? analyzed.commentary : null } : move;
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
  const currentBadgeMeta = currentMove?.is_theory
    ? CLASSIFICATION_META.theory
    : currentMove?.classification
    ? CLASSIFICATION_META[currentMove.classification as keyof typeof CLASSIFICATION_META]
    : null;
  const currentBadge = currentBadgeMeta && currentMove?.classification === "best" && !currentMove.is_theory && currentMove.move_san !== currentMove.best_move_san
    ? { ...currentBadgeMeta, iconTitle: "Один из лучших ходов" }
    : currentBadgeMeta;
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
    restoreVariationFocusRef.current = true;
    setAutoplay(false);
    setVariation(null);
    setVariationError(null);
  };

  useEffect(() => {
    if (variation && focusVariationRef.current) {
      focusVariationRef.current = false;
      variationContextRef.current?.focus();
    } else if (!variation && restoreVariationFocusRef.current) {
      restoreVariationFocusRef.current = false;
      const trigger = variationTriggerRef.current;
      if (trigger?.isConnected) trigger.focus();
      else boardControlRef.current?.focus();
    }
  }, [variation]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (showScoringHelp || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey
        || target instanceof HTMLElement && (target.isContentEditable || !!target.closest("input, textarea, select, summary, [role=dialog]"))) return;
      const index = variation?.index ?? currentMoveIndex;
      const end = variation?.moves.length ?? maxIndex;
      const next = event.key === "ArrowLeft" ? index - 1 : event.key === "ArrowRight" ? index + 1
        : event.key === "Home" ? 0 : event.key === "End" ? end : null;
      if (next === null) return;
      event.preventDefault();
      setAutoplay(false);
      const bounded = Math.max(0, Math.min(next, end));
      if (variation) setVariation((line) => line ? { ...line, index: bounded } : null);
      else goToMove(bounded);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [currentMoveIndex, maxIndex, variation, goToMove, showScoringHelp]);

  const closeScoringHelp = useCallback(() => setShowScoringHelp(false), []);

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
      else await api.startExplanations(gameId, recover ? analysis?.review?.owner_color ?? playerColor! : playerColor!, recover, expectedAttemptId, true);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Не удалось запустить задачу");
    } finally {
      await Promise.all([refetchStatus(), refetchAnalysis()]);
      setRequestBusy(false);
    }
  };

  const playLine = (kind: "played" | "best") => {
    if (!currentMove || currentMoveIndex === 0) return;
    setAutoplay(false);
    setVariationError(null);
    try {
      const line = readLine(kind === "played" ? currentMove.played_line : currentMove.best_line);
      if (line.length === 0) throw new Error("Проверенная линия недоступна.");
      if (line[0] !== (kind === "played" ? currentMove.move_san : currentMove.best_move_san)) throw new Error("Линия не соответствует ходу.");
      // Both verified lines start before the selected move, including the first SAN.
      const chess = new Chess(replay.positions[currentMoveIndex - 1]);
      const positions = [chess.fen()];
      for (const san of line.slice(0, 8)) {
        chess.move(san);
        positions.push(chess.fen());
      }
      variationTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      focusVariationRef.current = true;
      setVariation({ kind, title: kind === "played" ? "После сыгранного хода" : "Рекомендация движка", positions, moves: line.slice(0, 8), index: 1, startNumber: currentMove.move_number, startsBlack: currentMove.color === "black" });
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
  const commentaryComplete = moves.length > 0 && moves.every((move) => move.commentary?.version === 2);
  const reviewBusy = reviewStatus === "queued" || reviewStatus === "in_progress";
  const loadingReview = statusLoading || analysisLoading;
  const readFailed = !!statusError || !!analysisReadError;
  const engineReady = actualEngineStatus === "done" && analysis?.score_version === 1;
  const reviewFailed = reviewStatus === "failed" || reviewStatus === "partial";
  const actionDisabled = requestBusy || engineBusy || reviewBusy || loadingReview || readFailed;
  const showPreparation = loadingReview || readFailed || requestBusy || engineBusy || reviewBusy || !engineReady || !commentaryComplete || !!requestError;
  const moments = verifiedReview?.context?.moments ?? [];
  const boardIndex = variation?.index ?? currentMoveIndex;
  const boardMaxIndex = variation?.moves.length ?? maxIndex;
  const variationPly = variation ? Math.max(0, variation.index - 1) + (variation.startsBlack ? 1 : 0) : 0;
  const boardAnnouncement = variation
    ? `${variation.title}. ${variation.index === 0 ? "Позиция до хода" : `Ход ${variation.startNumber + Math.floor(variationPly / 2)}${variationPly % 2 ? "…" : "."} ${variation.moves[variation.index - 1]}. Полуход ${variation.index} из ${variation.moves.length}`}`
    : currentMove ? `Партия. Ход ${currentMove.move_number}${currentMove.color === "black" ? "…" : "."} ${currentMove.move_san}` : "Партия. Начальная позиция";

  return (
    <div className="space-y-5 font-coach">
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">{boardAnnouncement}</p>
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
          <p className="text-sm text-stone-600 dark:text-stone-300">
            {game.result} {game.eco_code} {game.opening_name ? ` - ${game.opening_name}` : ""}
          </p>
        </div>
      </div>

      {showPreparation && <section aria-label="Подготовка разбора" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-stone-200/60 p-3 text-sm dark:bg-chess-light">
        <p role={readFailed || requestError ? "alert" : "status"} className="max-w-prose text-stone-700 dark:text-stone-200">
          {readFailed ? "Не удалось загрузить разбор. Попробуйте ещё раз."
            : requestError ? "Не удалось запустить разбор. Сохранённые результаты доступны ниже."
            : loadingReview ? "Загружаем разбор…"
            : requestBusy ? "Отправляем запрос…"
            : engineBusy ? "Проверяем ходы. Партию уже можно листать."
            : reviewBusy ? "Готовим объяснения сыгранных ходов и рекомендаций. Готовые комментарии уже можно читать."
            : !engineReady ? actualEngineStatus === "failed" ? "Не удалось проверить ходы. Можно повторить анализ." : "Сначала проверим ходы, затем можно будет добавить объяснения."
            : !playerColor ? "Выберите сторону в учебных моментах. Комментарии будут доступны для обеих сторон."
            : reviewFailed ? "Не удалось закончить разбор. Готовые объяснения сохранены. Можно повторить попытку."
            : "Разбор объяснит сыгранные ходы и рекомендации движка для обеих сторон."}
        </p>
        {readFailed ? <NavButton onClick={() => { void refetchStatus(); void refetchAnalysis(); }} disabled={requestBusy}>Повторить загрузку</NavButton>
          : !engineBusy && !reviewBusy && !loadingReview && (!engineReady
            ? <NavButton primary onClick={() => void start("engine")} disabled={actionDisabled}>{actualEngineStatus === "failed" || actualEngineStatus === "done" ? "Повторить анализ" : "Проверить ходы"}</NavButton>
            : !commentaryComplete && <NavButton primary onClick={() => void start("review")} disabled={actionDisabled || !playerColor}>{reviewFailed ? "Повторить попытку" : "Разобрать партию"}</NavButton>)}
      </section>}

      {(engineBusy || reviewBusy || requestError || readFailed || reviewFailed || actualEngineStatus === "failed") && <details className="text-sm text-stone-600 dark:text-stone-300">
        <summary className="w-fit cursor-pointer py-1">Диагностика и восстановление</summary>
        <div className="mt-2 space-y-2 break-words rounded border border-stone-300 p-3 dark:border-stone-600">
          <p>Движок: {statusLabel(actualEngineStatus)}. Объяснения: {statusLabel(reviewStatus ?? "pending")}.</p>
          {(requestError || statusError || analysisReadError || status?.engine_error || analysis?.engine_error || status?.review_error || verifiedReview?.error) && <p>{requestError ?? statusError?.message ?? analysisReadError?.message ?? status?.engine_error ?? analysis?.engine_error ?? status?.review_error ?? verifiedReview?.error}</p>}
          {(engineBusy || reviewBusy) && <>
            <p>Ручное восстановление допустимо только после остановки прежнего worker. Долгое ожидание само по себе не означает сбой.</p>
            {(status?.heartbeat_at ?? analysis?.heartbeat_at) && <p>Последний heartbeat движка: {status?.heartbeat_at ?? analysis?.heartbeat_at}</p>}
            {engineBusy && <NavButton disabled={requestBusy || !analysis || readFailed} onClick={() => void start("engine", true)}>Восстановить анализ…</NavButton>}
            {reviewBusy && <NavButton disabled={requestBusy || !playerColor || analysis?.review?.player_color !== playerColor || readFailed} onClick={() => void start("review", true)}>Восстановить объяснения…</NavButton>}
          </>}
        </div>
      </details>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-4">
          <div className="flex items-center justify-between gap-2 pl-12 text-sm">
            <p className="text-stone-600 dark:text-stone-300">{variation ? "Просмотр варианта" : "Партия"}</p>
            <button type="button" onClick={() => setRotated((value) => !value)} className="min-h-10 rounded px-2 text-stone-700 hover:bg-stone-200 dark:text-stone-200 dark:hover:bg-stone-700">↻ Повернуть доску</button>
          </div>
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
              <h3 ref={variationContextRef} tabIndex={-1} className="font-semibold">{variation.title} · {variation.index === 0 ? "До хода" : `${variation.index} / ${variation.moves.length}`}</h3>
              <p className="text-stone-600 dark:text-stone-300">Возможное продолжение, не ходы партии.</p>
              <div className="flex flex-wrap gap-1" aria-label="Ходы линии движка">
                <NavButton active={variation.index === 0} onClick={() => navigateBoard(0)}>До хода</NavButton>
                {variation.moves.map((san, index) => {
                  const ply = index + (variation.startsBlack ? 1 : 0);
                  const label = `${variation.startNumber + Math.floor(ply / 2)}${ply % 2 ? "…" : "."} ${san}`;
                  return <NavButton key={index} active={variation.index === index + 1} onClick={() => navigateBoard(index + 1)}>{label}</NavButton>;
                })}
              </div>
              <NavButton onClick={returnToGame}>Вернуться к партии</NavButton>
            </div>}
            {variationError && <p role="alert" className="text-sm text-red-400">{variationError}</p>}
            <div className="flex flex-wrap gap-2">
              <NavButton onClick={() => navigateBoard(0)} disabled={boardIndex === 0}>
                ⏮ В начало
              </NavButton>
              <NavButton buttonRef={boardControlRef} onClick={() => navigateBoard(boardIndex - 1)} disabled={boardIndex === 0}>
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
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <section aria-label="Объяснение хода" className="space-y-3 rounded-lg border border-stone-300 bg-white/70 p-4 dark:border-stone-600 dark:bg-chess-light/30">
            {variation && <p className="text-sm text-stone-600 dark:text-stone-300">Объяснение хода из партии. На доске открыт вариант.</p>}
            <CommentaryPanel
              key={currentMove?.id ?? "summary"}
              move={currentMove}
              summary={verifiedReview?.summary}
              loading={loadingReview}
              generating={reviewBusy}
              onPlayLine={playLine}
              activeVariationKind={variation?.kind}
              playedLineAvailable={readLine(currentMove?.played_line).length > 0}
              bestLineAvailable={readLine(currentMove?.best_line).length > 0}
            />
          </section>

          {moves.length > 0 && <MoveList moves={moves} currentMoveIndex={currentMoveIndex} onSelectMove={goToMove} />}

          <section className="space-y-3 rounded-lg border border-stone-300 p-4 text-sm dark:border-stone-600">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-stone-800 dark:text-stone-100">Учебные моменты</h2>
              <div className="flex items-center gap-2">
                <label htmlFor="review-color" className="sr-only">Сторона для учебных моментов</label>
                <select id="review-color" value={playerColor ?? ""} disabled={requestBusy} onChange={(event) => { setChosenColor(event.target.value as PlayerColor); setRequestError(null); setVariation(null); setVariationError(null); setAutoplay(false); }} className="min-h-10 max-w-full rounded border border-stone-400 bg-white px-2 py-1 dark:border-stone-600 dark:bg-chess-dark">
                  <option value="" disabled>Выберите сторону</option>
                  <option value="white">За белых</option>
                  <option value="black">За чёрных</option>
                </select>
              </div>
            </div>
            {moments.length ? <div className="flex flex-wrap gap-2">{moments.map((moment) => <NavButton key={moment.move_index} active={currentMoveIndex === moment.move_index + 1} onClick={() => goToMove(moment.move_index + 1)}>{moment.move_number}{moment.color === "white" ? "." : "…"} {moment.move_san}</NavButton>)}</div> : <p className="text-stone-600 dark:text-stone-300">{loadingReview ? "Загружаем подборку…" : !playerColor ? "Выберите, за какую сторону хотите разобрать ошибки." : verifiedReview ? "В этой подборке нет ошибок для выбранной стороны. Остальные ходы можно изучать по порядку." : "Подборка появится после подготовки разбора."}</p>}
          </section>
          {!!verifiedReview?.recommendations.length && <section className="rounded-lg border border-stone-300 p-4 text-sm dark:border-stone-600"><h2 className="mb-2 font-semibold">Что тренировать</h2><ul className="list-inside list-disc space-y-2">{verifiedReview.recommendations.map((text, index) => <li key={index}>{text}</li>)}</ul></section>}

          <AnalysisLegend onOpenHelp={() => setShowScoringHelp(true)} />
        </div>
      </div>

      <ScoringHelpDrawer
        isOpen={showScoringHelp}
        onClose={closeScoringHelp}
      />
    </div>
  );
}

function NavButton({
  children,
  onClick,
  disabled,
  active,
  primary,
  buttonRef,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  primary?: boolean;
  buttonRef?: React.Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`min-h-10 rounded px-2 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        active || primary
          ? "bg-chess-highlight text-white hover:bg-[#3f6a4c]"
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
