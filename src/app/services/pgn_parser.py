from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import date

import chess
import chess.pgn

from app.core.exceptions import PGNParseError

logger = logging.getLogger(__name__)

# Unlike python-chess's searching tokenizer, these patterns must match at the
# current position and consume each complete token. Comments are handled below.
_MOVE_NUMBER = re.compile(r"[0-9]+\.(?:\.\.)?|\.\.\.")
_HEADER_PAIR = re.compile(
    r'\[([A-Za-z0-9][A-Za-z0-9_+#=:-]*)\s+"((?:[^"\\\r\n]|\\["\\])*)"\s*\]'
)
_MOVETEXT_TOKEN = re.compile(
    r"(?:(?P<move>[NBKRQ]?[a-h]?[1-8]?[\-x]?[a-h][1-8](?:=?[nbrqkNBRQK])?[+#]?"
    r"|(?:O-O(?:-O)?|0-0(?:-0)?)[+#]?)"
    r"|\$[0-9]+|[!?]{1,2}|(?P<result>1/2-1/2|1-0|0-1|\*))"
    r"(?=$|[\s{}();$!?])"
)


def _validate_pgn_header(name: str, value: str) -> None:
    if name == "FEN" or (name == "SetUp" and value != "0"):
        raise PGNParseError("Позиции PGN FEN/SetUp пока не поддерживаются")
    if name == "Variant" and value.lower() not in {"standard", "chess", "normal"}:
        raise PGNParseError("Шахматные варианты PGN пока не поддерживаются")


def _normalize_pgn_headers(line: str, line_number: int) -> str:
    """Split complete tag pairs without treating quoted brackets as delimiters."""
    headers: list[str] = []
    position = 0
    while position < len(line):
        if line[position].isspace():
            position += 1
            continue
        header = _HEADER_PAIR.match(line, position)
        if header is None:
            raise PGNParseError(f"Некорректный заголовок PGN в строке {line_number}")
        name, value = header.groups()
        _validate_pgn_header(name, value)
        headers.append(f'[{name} "{value}"]')
        position = header.end()
    return "\n".join(headers)


def _consume_pgn_token(
    line: str, position: int, line_number: int, preceding_moves: list[bool]
) -> int:
    if line[position] == "(":
        if not preceding_moves[-1]:
            raise PGNParseError(
                f"Вариант PGN без предшествующего хода в строке {line_number}"
            )
        preceding_moves.append(False)
        return position + 1
    if line[position] == ")" and len(preceding_moves) > 1:
        preceding_moves.pop()
        return position + 1
    token = _MOVE_NUMBER.match(line, position) or _MOVETEXT_TOKEN.match(line, position)
    if token is None:
        raise PGNParseError(f"Некорректный токен PGN в строке {line_number}")
    if token.lastgroup in {"move", "result"}:
        preceding_moves[-1] = token.lastgroup == "move"
    return token.end()


def _validate_pgn_tokens(pgn_text: str) -> str:
    """Validate every token and normalize headers for python-chess's reader."""
    in_comment = False
    preceding_moves = [False]
    lines = pgn_text.lstrip("\ufeff").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not in_comment and line.startswith("%"):
            continue
        if not in_comment and len(preceding_moves) == 1 and line.lstrip().startswith("["):
            lines[line_number - 1] = _normalize_pgn_headers(line, line_number)
            preceding_moves[-1] = False
            continue
        if not in_comment and not line.strip():
            preceding_moves[-1] = False

        position = 0
        while position < len(line) and (in_comment or line[position] != ";"):
            if in_comment:
                end = line.find("}", position)
                if end < 0:
                    break
                in_comment = False
                position = end + 1
                continue
            char = line[position]
            if char == "{":
                in_comment = True
            elif not char.isspace():
                position = _consume_pgn_token(line, position, line_number, preceding_moves)
                continue
            position += 1

    if in_comment or len(preceding_moves) > 1:
        raise PGNParseError("Не закрыт комментарий или вариант PGN")
    return "\n".join(lines)


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

        Returns a list of ParsedGame objects, or raises PGNParseError if any
        game is empty, invalid, or uses an unsupported starting position.
        """
        if not pgn_text.strip():
            raise PGNParseError("Текст PGN пуст")
        pgn_text = _validate_pgn_tokens(pgn_text)
        games: list[ParsedGame] = []
        pgn_io = io.StringIO(pgn_text)

        while True:
            try:
                game = chess.pgn.read_game(pgn_io)
            except ValueError as error:
                raise PGNParseError(f"Некорректный PGN: {error}") from error
            if game is None:
                break
            if game.errors:
                raise PGNParseError(f"Некорректный PGN: {game.errors[0]}") from game.errors[0]
            parsed = self._extract_game_data(game)
            if not parsed.moves:
                raise PGNParseError("В партии PGN нет ходов основной линии")
            games.append(parsed)

        if not games:
            raise PGNParseError("В PGN не найдено партий")
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
