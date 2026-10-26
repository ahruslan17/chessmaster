import { Chessboard } from "react-chessboard";
import { Chess } from "chess.js";
import { useEffect, useId, useMemo, useState } from "react";
import { useTheme } from "../contexts/ThemeContext";

type Square = string;

interface ChessBoardProps {
  position: string;
  orientation?: "white" | "black";
  lastMove?: { from: Square; to: Square } | null;
  /** When set, show a classification badge in top-right of this square. */
  moveBadge?: {
    square: Square;
    iconSrc: string;
    title: string;
  } | null;
  boardWidth?: number;
}

const SQUARE_COLORS_DARK = {
  light: "#4a5568",
  dark: "#2d3748",
  lastMove: "#6b7280",
};

const SQUARE_COLORS_LIGHT = {
  light: "#f0d9b5",
  dark: "#b58863",
  lastMove: "#cdd26a",
};

/** Arrow from last move (from → to), chess.com style — bright green */
const LAST_MOVE_ARROW_COLOR = "rgba(72, 187, 120, 0.95)";

const BADGE_SIZE = 32;

/** Chess square (e.g. "e5") to column and row indices, white view: a8 = (0,0), h1 = (7,7). */
function squareToIndices(sq: Square): { col: number; row: number } {
  const file = sq.charCodeAt(0) - 97;
  const rank = 8 - parseInt(sq[1]!, 10);
  return { col: file, row: rank };
}

export function ChessBoard({
  position,
  orientation = "white",
  lastMove = null,
  moveBadge = null,
  boardWidth = 560,
}: ChessBoardProps) {
  const frameSize = boardWidth + 8;
  const { theme } = useTheme();
  const colors = theme === "dark" ? SQUARE_COLORS_DARK : SQUARE_COLORS_LIGHT;
  const descriptionId = useId();
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  const positionDescription = useMemo(() => {
    const chess = new Chess(position);
    const names = { k: "король", q: "ферзь", r: "ладья", b: "слон", n: "конь", p: "пешка" };
    const pieces = chess.board().flat().filter((piece) => piece !== null);
    return [
      `Шахматная доска. ${orientation === "white" ? "Белые" : "Чёрные"} снизу. Ход ${chess.turn() === "w" ? "белых" : "чёрных"}.`,
      ...(["w", "b"] as const).map((color) => `${color === "w" ? "Белые" : "Чёрные"}: ${pieces.filter((piece) => piece.color === color).map((piece) => `${names[piece.type]} ${piece.square}`).join(", ")}.`),
    ].join(" ");
  }, [position, orientation]);

  const customSquareStyles: Record<string, React.CSSProperties> = {};
  if (lastMove) {
    customSquareStyles[lastMove.from] = {
      backgroundColor: colors.lastMove,
    };
    customSquareStyles[lastMove.to] = {
      backgroundColor: colors.lastMove,
    };
  }

  const customArrows = lastMove
    ? ([[lastMove.from, lastMove.to, LAST_MOVE_ARROW_COLOR]] as React.ComponentProps<
        typeof Chessboard
      >["customArrows"])
    : undefined;

  const cell = boardWidth / 8;
  let badgeStyle: React.CSSProperties | null = null;
  if (moveBadge) {
    const { col, row } = squareToIndices(moveBadge.square);
    const displayCol = orientation === "black" ? 7 - col : col;
    const displayRow = orientation === "black" ? 7 - row : row;
    const left = (displayCol + 1) * cell - BADGE_SIZE;
    const top = displayRow * cell;
    badgeStyle = {
      position: "absolute",
      left,
      top,
      width: BADGE_SIZE,
      height: BADGE_SIZE,
      pointerEvents: "none",
      zIndex: 10,
    };
  }

  return (
    <div
      role="img"
      aria-describedby={descriptionId}
      aria-label="Позиция на шахматной доске"
      className="relative flex items-center justify-center overflow-hidden rounded-md border-2 border-stone-400 shadow-xl dark:border-stone-600"
      style={{ width: frameSize, height: frameSize }}
    >
      <span id={descriptionId} className="sr-only">{positionDescription}</span>
      <div aria-hidden="true">
      <Chessboard
        position={position}
        boardOrientation={orientation}
        boardWidth={boardWidth}
        customBoardStyle={{
          borderRadius: "0px",
        }}
        customDarkSquareStyle={{ backgroundColor: colors.dark }}
        customLightSquareStyle={{ backgroundColor: colors.light }}
        customSquareStyles={customSquareStyles}
        customArrows={customArrows}
        customArrowColor={LAST_MOVE_ARROW_COLOR}
        areArrowsAllowed={false}
        arePiecesDraggable={false}
        showBoardNotation={true}
        animationDuration={reducedMotion ? 0 : 200}
      />
      </div>
      {badgeStyle && (
        <img
          src={moveBadge?.iconSrc}
          alt={moveBadge?.title ?? "Move classification"}
          title={moveBadge?.title}
          style={badgeStyle}
          className="opacity-90"
        />
      )}
    </div>
  );
}
