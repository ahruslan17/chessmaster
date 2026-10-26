"""Deterministic, engine-only coaching context; no persistence or LLM calls."""

from __future__ import annotations

import io
from dataclasses import dataclass, replace

import chess
import chess.pgn

from app.services.opening_matcher import OpeningMatcher
from app.services.stockfish_analyzer import MoveEvaluation, classify_evaluation

MAX_MOMENTS = 5
MAX_LINE_PLIES = 6
_ENDGAME_MAX_PIECES = 6
_OPENING_MAX_MOVE = 10
_NEARBY_PLIES = 4
_REPEATED_EPISODE_PLIES = 8
_SEVERITY = {"inaccuracy": 1, "mistake": 2, "blunder": 3}
_PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}


@dataclass(frozen=True)
class _Moment:
    index: int
    evaluation: MoveEvaluation
    fen_before: str
    fen_after: str
    best_move_san: str
    played_line: list[str]
    best_line: list[str]
    facts: list[str]
    phase: str
    consequence: tuple[str, ...]
    mate_transition: bool

    def to_json(self) -> dict[str, object]:
        ev = self.evaluation
        return {
            "move_index": self.index,
            "move_number": ev.move_number,
            "color": ev.color,
            "fen_before": self.fen_before,
            "fen_after": self.fen_after,
            "move_san": ev.move_san,
            "best_move_san": self.best_move_san,
            "score_before": ev.score_before.to_json() if ev.score_before is not None else None,
            "score_after": ev.score_after.to_json() if ev.score_after is not None else None,
            "centipawn_loss": ev.centipawn_loss,
            "classification": ev.classification,
            "played_line": self.played_line,
            "best_line": self.best_line,
            "facts": self.facts,
            "verification": "engine",
        }


def _verified_line(
    board: chess.Board, proposed: list[str], anchor: str, label: str,
) -> tuple[list[str], list[str], set[str]]:
    """Keep only a legal, correctly anchored prefix and derive board facts."""
    replay = board.copy()
    line: list[str] = []
    facts: list[str] = []
    consequences: set[str] = set()
    try:
        first = replay.parse_san(anchor)
    except ValueError:
        return [], [f"{label}: no legal engine alternative is available."], consequences
    if not proposed or proposed[0] != replay.san(first):
        proposed = [replay.san(first)]
        facts.append(f"{label}: continuation evidence is absent or has the wrong anchor.")
    for san in proposed[:MAX_LINE_PLIES]:
        try:
            move = replay.parse_san(san)
        except ValueError:
            facts.append(f"{label}: invalid continuation omitted after {len(line)} plies.")
            break
        # python-chess accepts null SAN, but null moves are not legal chess moves.
        if not replay.is_legal(move):
            facts.append(f"{label}: illegal continuation omitted after {len(line)} plies.")
            break
        canonical = replay.san(move)
        mover = "white" if replay.turn else "black"
        captured = replay.piece_at(move.to_square)
        captured_square = move.to_square
        if replay.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not replay.turn)
            captured_square = move.to_square - 8 if replay.turn else move.to_square + 8
        line.append(canonical)
        if captured is not None:
            piece_name = _PIECE_NAMES[captured.piece_type]
            facts.append(
                f"{label} ply {len(line)}: {mover} captures a {piece_name} "
                f"on {chess.square_name(captured_square)}."
            )
            consequences.add(f"capture:{piece_name}")
        replay.push(move)
        if replay.is_checkmate():
            facts.append(f"{label} ply {len(line)}: {mover} delivers checkmate.")
            consequences.add("checkmate")
        elif replay.is_check():
            facts.append(f"{label} ply {len(line)}: {mover} gives check.")
            consequences.add("check")
        if move.promotion:
            piece_name = _PIECE_NAMES[move.promotion]
            facts.append(f"{label} ply {len(line)}: {mover} promotes to {piece_name}.")
            consequences.add("promotion")
    return line, facts, consequences


def _phase(board: chess.Board) -> str:
    non_pawn_material = sum(
        len(board.pieces(piece, color))
        for piece in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for color in chess.COLORS
    )
    if non_pawn_material <= _ENDGAME_MAX_PIECES:
        return "endgame"
    return "opening" if board.fullmove_number <= _OPENING_MAX_MOVE else "middlegame"


def _build_moment(index: int, board: chess.Board, ev: MoveEvaluation) -> _Moment:
    played_line, played_facts, played_events = _verified_line(
        board, ev.played_line, ev.move_san, "played_line",
    )
    candidate = next((cm for cm in ev.top_moves if cm.move_san == ev.best_move_san), None)
    best_line, best_facts, best_events = _verified_line(
        board, candidate.pv_san if candidate else [], ev.best_move_san, "best_line",
    )
    after = board.copy()
    after.push_san(ev.move_san)
    facts = [*played_facts, *best_facts]
    if not played_events and not best_events:
        facts.append("No capture, check, checkmate or promotion in the verified short lines.")
    if ev.score_before is None or ev.score_after is None:
        facts.append("Exact cp/mate evidence is unavailable; legacy floats do not establish mate.")
    elif ev.score_before.mate_winner != ev.score_after.mate_winner:
        if ev.score_after.mate_winner is not None:
            facts.append(
                f"Engine score after the move reports mate for {ev.score_after.mate_winner}."
            )
        if ev.score_before.mate_winner == ev.color:
            facts.append("Engine score no longer reports the mover's previously forced mate.")
    if len(played_line) == 1 and not after.is_game_over():
        facts.append("No verified engine reply after the played move is available.")
    facts.append("Tactical motive is not verified; legal lines alone do not prove a motif.")
    mate_transition = (
        ev.score_before is not None and ev.score_after is not None
        and ev.score_before.mate_winner != ev.score_after.mate_winner
    )
    return _Moment(
        index=index, evaluation=ev, fen_before=board.fen(), fen_after=after.fen(),
        best_move_san=best_line[0] if best_line else "", played_line=played_line,
        best_line=best_line, facts=facts, phase=_phase(board),
        consequence=tuple(sorted(
            {f"played:{event}" for event in played_events}
            | {f"best:{event}" for event in best_events}
        )),
        mate_transition=mate_transition,
    )


def _select_moments(candidates: list[_Moment]) -> list[_Moment]:
    """Favor severity and evidence, then spread phases, consequences and timing."""
    selected: list[_Moment] = []
    remaining = list(candidates)
    while remaining and len(selected) < MAX_MOMENTS:
        def priority(moment: _Moment) -> tuple[int, int, float, int]:
            nearby = any(
                abs(moment.index - other.index) <= _NEARBY_PLIES for other in selected
            )
            value = (
                4 * _SEVERITY[moment.evaluation.classification]
                + 5 * moment.mate_transition
                + 2 * bool(moment.consequence)
                + 3 * all(moment.phase != other.phase for other in selected)
                + 2 * all(moment.consequence != other.consequence for other in selected)
                - 6 * nearby
            )
            # Diversity must never let a lower-severity episode suppress a blunder.
            return (
                _SEVERITY[moment.evaluation.classification], value,
                moment.evaluation.centipawn_loss, -moment.index,
            )

        chosen = max(remaining, key=priority)
        remaining.remove(chosen)
        # Adjacent repeated errors usually explain one episode, not separate lessons.
        if any(
            abs(chosen.index - other.index) < _REPEATED_EPISODE_PLIES
            and chosen.phase == other.phase
            and chosen.consequence == other.consequence
            and chosen.mate_transition == other.mate_transition
            for other in selected
        ):
            continue
        selected.append(chosen)
    return sorted(selected, key=lambda moment: moment.index)


def build_review_context(
    pgn_text: str, evaluations: list[MoveEvaluation], player_color: str,
    *, include_all_moves: bool = False,
) -> dict[str, object]:
    """Build reusable side-specific JSON context from matching engine evaluations.

    Alignment failures reject the whole context instead of attaching trustworthy
    engine evidence to the wrong game. Missing or corrupt PVs are explicitly
    marked and never presented as legal continuations.
    """
    if player_color not in ("white", "black"):
        raise ValueError("player_color must be white or black")
    stream = io.StringIO(pgn_text)
    game = chess.pgn.read_game(stream)
    if game is None or game.errors or chess.pgn.read_game(stream) is not None:
        raise ValueError("Review requires one valid PGN game")
    moves = list(game.mainline_moves())
    if len(moves) != len(evaluations):
        raise ValueError("Engine evaluations do not match PGN length")
    board = game.board()
    candidates: list[_Moment] = []
    all_moments: list[dict[str, object]] = []
    candidates_by_color: dict[str, list[_Moment]] = {"white": [], "black": []}
    opening = OpeningMatcher().match(moves) if include_all_moves else None
    for index, (move, ev) in enumerate(zip(moves, evaluations, strict=True)):
        color = "white" if board.turn else "black"
        if (
            not board.is_legal(move) or ev.move_san != board.san(move)
            or ev.color != color or ev.move_number != board.fullmove_number
        ):
            raise ValueError(f"Engine evaluation does not match PGN at ply {index}")
        if color == player_color or include_all_moves:
            if ev.score_before is not None and ev.score_after is not None and (
                ev.score_before.mate is not None or ev.score_after.mate is not None
            ):
                ev = replace(ev, classification=classify_evaluation(
                    ev.eval_before, ev.eval_after, board.turn, ev.score_before, ev.score_after,
                ))
            moment = _build_moment(index, board, ev)
            if include_all_moves:
                entry = moment.to_json()
                entry["is_theory"] = opening is not None and index < opening.move_count
                all_moments.append(entry)
            if ev.classification in _SEVERITY:
                candidates_by_color[color].append(moment)
                if color == player_color:
                    candidates.append(moment)
        board.push(move)
    context = {
        "version": 1, "player_color": player_color,
        "moments": [moment.to_json() for moment in _select_moments(candidates)],
        "perspective": "white",
    }
    if include_all_moves:
        context.update({
            "commentary_scope": "all_moves", "moves": all_moments,
            "moments_by_color": {
                color: [moment.to_json() for moment in _select_moments(items)]
                for color, items in candidates_by_color.items()
            },
        })
    return context
