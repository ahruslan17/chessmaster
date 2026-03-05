from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date

import chess
import chess.pgn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedGame:
    """Structured data extracted from a single PGN game."""

    pgn_text: str
    white_player: str
    black_player: str
    result: str
    opening_name: str | None
    eco_code: str | None
    time_control: str | None
    played_at: date | None
    moves: list[chess.Move]
    headers: dict[str, str]


class PGNParserService:
    """Parses PGN text into structured game data using python-chess."""

    def parse_pgn(self, pgn_text: str) -> list[ParsedGame]:
        """Parse PGN text containing one or more games.

        Returns a list of ParsedGame objects.
        Games that fail to parse are skipped with a warning.
        """
        games: list[ParsedGame] = []
        pgn_io = io.StringIO(pgn_text)

        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break

            try:
                parsed = self._extract_game_data(game)
                games.append(parsed)
            except Exception:
                logger.warning("Failed to parse a game from PGN, skipping", exc_info=True)

        logger.info("Parsed %d game(s) from PGN input", len(games))
        return games

    def _extract_game_data(self, game: chess.pgn.Game) -> ParsedGame:
        """Extract structured data from a python-chess Game object."""
        headers = dict(game.headers)
        moves = list(game.mainline_moves())

        # Reconstruct this single game's PGN text
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        single_pgn = game.accept(exporter)

        return ParsedGame(
            pgn_text=str(single_pgn),
            white_player=headers.get("White", "?"),
            black_player=headers.get("Black", "?"),
            result=headers.get("Result", "*"),
            opening_name=headers.get("Opening"),
            eco_code=headers.get("ECO"),
            time_control=headers.get("TimeControl"),
            played_at=_parse_pgn_date(headers.get("Date", "")),
            moves=moves,
            headers=headers,
        )


def _parse_pgn_date(date_str: str) -> date | None:
    """Parse PGN date format (YYYY.MM.DD) into a Python date.

    Returns None for missing, partial ('2024.01.??'), or malformed dates.
    """
    if not date_str or "?" in date_str:
        return None
    pgn_date_parts_count = 3
    try:
        parts = date_str.split(".")
        if len(parts) != pgn_date_parts_count:
            return None
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None
