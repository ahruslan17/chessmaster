import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Chess } from "chess.js";
import { useGame } from "../hooks/useGames";
import { useAnalysis, useAnalysisStatus } from "../hooks/useAnalysis";
import { ChessBoard } from "../components/ChessBoard";
import { MoveList } from "../components/MoveList";
import { CommentaryPanel } from "../components/CommentaryPanel";
import { EvalBar } from "../components/EvalBar";

const INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function GameViewer() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const [currentMoveIndex, setCurrentMoveIndex] = useState(0);
  const [autoplay, setAutoplay] = useState(false);

  const { data: game, isLoading: gameLoading, error: gameError } = useGame(gameId ?? null);
  const { data: analysis, refetch: refetchAnalysis } = useAnalysis(gameId ?? null);
  const { data: status } = useAnalysisStatus(gameId ?? null);

  // Build FEN at each move index from PGN
  const positions = useBuildPositions(game?.pgn_text);
  const currentFen = positions[currentMoveIndex] ?? INITIAL_FEN;
  const currentMove =
    currentMoveIndex > 0 && analysis?.moves[currentMoveIndex - 1]
      ? analysis.moves[currentMoveIndex - 1]
      : null;
  const lastMoveSquares = useLastMoveSquares(game?.pgn_text, currentMoveIndex);

  // Eval: use eval_after of the previous move (position after last move)
  const evalCp = currentMoveIndex > 0 && analysis?.moves[currentMoveIndex - 1]?.eval_after != null
    ? analysis.moves[currentMoveIndex - 1].eval_after!
    : 0;

  const orientation = (game?.player_color === "black" ? "black" : "white") as "white" | "black";
  const maxIndex = analysis?.moves.length ?? 0;

  // Refetch analysis when status becomes done
  useEffect(() => {
    if (status?.status === "done") {
      refetchAnalysis();
    }
  }, [status?.status, refetchAnalysis]);

  // Autoplay
  useEffect(() => {
    if (!autoplay || currentMoveIndex >= maxIndex) {
      setAutoplay(false);
      return;
    }
    const t = setTimeout(() => setCurrentMoveIndex((i) => i + 1), 800);
    return () => clearTimeout(t);
  }, [autoplay, currentMoveIndex, maxIndex]);

  const goToMove = useCallback((index: number) => {
    setCurrentMoveIndex(Math.max(0, Math.min(index, maxIndex)));
  }, [maxIndex]);

  if (gameLoading || !gameId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-stone-600 dark:text-stone-500">Loading game...</p>
      </div>
    );
  }

  if (gameError || !game) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-400">Game not found</p>
        <button
          onClick={() => navigate("/")}
          className="mt-4 text-chess-highlight hover:underline dark:text-chess-highlight"
        >
          Back to games
        </button>
      </div>
    );
  }

  const analysisReady = analysis && status?.status === "done";
  const isAnalyzing = status?.status === "pending" || status?.status === "in_progress";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate("/")}
          className="text-stone-600 transition hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
        >
          ← Back to games
        </button>
        <div className="text-center">
          <h1 className="text-lg font-semibold text-stone-800 dark:text-stone-100">
            {game.white_player} vs {game.black_player}
          </h1>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {game.result} {game.opening_name ? `• ${game.opening_name}` : ""}
          </p>
        </div>
        <div className="w-24" />
      </div>

      {isAnalyzing && (
        <div className="rounded-lg border border-chess-inaccuracy/50 bg-chess-inaccuracy/10 px-4 py-2 text-sm text-chess-inaccuracy">
          Analysis in progress... This may take a few minutes.
        </div>
      )}

      <div className="flex gap-6">
        <div className="flex items-start gap-4">
          <EvalBar
            evalCentipawns={evalCp}
            orientation={orientation}
            height={560}
          />
          <ChessBoard
            position={currentFen}
            orientation={orientation}
            lastMove={lastMoveSquares}
            theoryBadgeSquare={
              currentMove?.classification === "theory" && lastMoveSquares
                ? lastMoveSquares.to
                : null
            }
            boardWidth={Math.min(560, typeof window !== "undefined" ? window.innerWidth - 320 : 560)}
          />
        </div>

        <div className="flex flex-1 flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <NavButton
              onClick={() => goToMove(0)}
              disabled={currentMoveIndex === 0}
            >
              ⏮ First
            </NavButton>
            <NavButton
              onClick={() => goToMove(currentMoveIndex - 1)}
              disabled={currentMoveIndex === 0}
            >
              ← Prev
            </NavButton>
            <NavButton
              onClick={() => goToMove(currentMoveIndex + 1)}
              disabled={currentMoveIndex >= maxIndex}
            >
              Next →
            </NavButton>
            <NavButton
              onClick={() => goToMove(maxIndex)}
              disabled={currentMoveIndex >= maxIndex}
            >
              Last ⏭
            </NavButton>
            <NavButton
              onClick={() => setAutoplay((a) => !a)}
              disabled={currentMoveIndex >= maxIndex}
              active={autoplay}
            >
              {autoplay ? "⏸ Pause" : "▶ Autoplay"}
            </NavButton>
          </div>

          {analysisReady && analysis.moves.length > 0 && (
            <MoveList
              moves={analysis.moves}
              currentMoveIndex={currentMoveIndex}
              onSelectMove={goToMove}
            />
          )}

          <CommentaryPanel
            move={currentMove}
            summary={analysis?.summary ?? undefined}
          />
        </div>
      </div>
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

function useBuildPositions(pgnText: string | undefined): string[] {
  const [positions, setPositions] = useState<string[]>([INITIAL_FEN]);

  useEffect(() => {
    if (!pgnText?.trim()) {
      setPositions([INITIAL_FEN]);
      return;
    }
    try {
      const chess = new Chess();
      chess.loadPgn(pgnText);
      const history = chess.history();
      const fens: string[] = [INITIAL_FEN];
      const replay = new Chess();
      for (const move of history) {
        const result = replay.move(move);
        if (result) fens.push(replay.fen());
      }
      setPositions(fens);
    } catch {
      setPositions([INITIAL_FEN]);
    }
  }, [pgnText]);

  return positions;
}

function useLastMoveSquares(
  pgnText: string | undefined,
  moveIndex: number
): { from: string; to: string } | null {
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);

  useEffect(() => {
    if (!pgnText?.trim() || moveIndex < 1) {
      setLastMove(null);
      return;
    }
    try {
      const chess = new Chess();
      chess.loadPgn(pgnText);
      const history = chess.history({ verbose: true });
      const move = history[moveIndex - 1];
      if (move && "from" in move && "to" in move) {
        setLastMove({ from: move.from, to: move.to });
      } else {
        setLastMove(null);
      }
    } catch {
      setLastMove(null);
    }
  }, [pgnText, moveIndex]);

  return lastMove;
}
