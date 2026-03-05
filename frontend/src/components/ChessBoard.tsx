import { Chessboard } from "react-chessboard";
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
  const { theme } = useTheme();
  const colors = theme === "dark" ? SQUARE_COLORS_DARK : SQUARE_COLORS_LIGHT;

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
    <div className="relative overflow-hidden rounded-lg border border-stone-400 shadow-xl dark:border-stone-600">
      <Chessboard
        position={position}
        boardOrientation={orientation}
        boardWidth={boardWidth}
        customBoardStyle={{
          borderRadius: "4px",
        }}
        customDarkSquareStyle={{ backgroundColor: colors.dark }}
        customLightSquareStyle={{ backgroundColor: colors.light }}
        customSquareStyles={customSquareStyles}
        customArrows={customArrows}
        customArrowColor={LAST_MOVE_ARROW_COLOR}
        areArrowsAllowed={false}
        showBoardNotation={true}
        animationDuration={200}
      />
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
