from __future__ import annotations

import io
import json
from dataclasses import replace
from itertools import pairwise

import chess
import chess.pgn
import pytest

from app.services.review_moments import build_review_context
from app.services.stockfish_analyzer import CandidateMove, EngineScore, MoveEvaluation
from app.utils.chess_helpers import classify_move


def _evaluations(pgn: str) -> list[MoveEvaluation]:
    game = chess.pgn.read_game(io.StringIO(pgn))
    assert game is not None
    board = game.board()
    evaluations = []
    for move in game.mainline_moves():
        san = board.san(move)
        evaluations.append(MoveEvaluation(
            move_number=board.fullmove_number, color="white" if board.turn else "black",
            move_san=san, best_move_san=san, eval_before=0.0, eval_after=0.0,
            centipawn_loss=0.0, classification="best",
            score_before=EngineScore(cp=0.0), score_after=EngineScore(cp=0.0),
            played_line=[san], top_moves=[CandidateMove(san, 0.0, [san], EngineScore(cp=0.0))],
        ))
        board.push(move)
    return evaluations


def _error(ev: MoveEvaluation, **kwargs) -> MoveEvaluation:
    return replace(ev, **{"classification": "mistake", "centipawn_loss": 170.0, **kwargs})


def test_both_colors_reuse_evaluations_without_mutation() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 *"
    evaluations = [_error(ev) for ev in _evaluations(pgn)]
    original = list(evaluations)
    white = build_review_context(pgn, evaluations, "white")
    black = build_review_context(pgn, evaluations, "black")
    assert white["version"] == 1
    assert white["perspective"] == "white"
    assert white["player_color"] == "white"
    assert {m["color"] for m in white["moments"]} == {"white"}
    assert {m["color"] for m in black["moments"]} == {"black"}
    assert {m["move_index"] for m in white["moments"]}.isdisjoint(
        m["move_index"] for m in black["moments"]
    )
    assert evaluations == original
    assert json.loads(json.dumps(white)) == white
    assert build_review_context(pgn, evaluations, "white") == white


def test_only_own_errors_and_no_forced_five() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 *"
    evaluations = _evaluations(pgn)
    evaluations[0] = replace(evaluations[0], classification="theory")
    evaluations[1] = _error(evaluations[1], classification="blunder")
    evaluations[2] = _error(evaluations[2], classification="inaccuracy")
    context = build_review_context(pgn, evaluations, "white")
    assert [m["move_index"] for m in context["moments"]] == [2]
    assert build_review_context(pgn, _evaluations(pgn), "white")["moments"] == []


def test_full_context_contains_every_ply_even_without_errors() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 *"
    context = build_review_context(pgn, _evaluations(pgn), "white", include_all_moves=True)
    assert context["commentary_scope"] == "all_moves"
    assert [move["move_index"] for move in context["moves"]] == [0, 1, 2, 3]
    assert [move["color"] for move in context["moves"]] == ["white", "black"] * 2
    assert all(move["is_theory"] for move in context["moves"])
    assert context["moments_by_color"] == {"white": [], "black": []}


def test_full_context_keeps_key_moments_separate_by_color() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 *"
    evaluations = [_error(ev) for ev in _evaluations(pgn)]
    context = build_review_context(pgn, evaluations, "white", include_all_moves=True)
    assert len(context["moves"]) == 4
    for color in ("white", "black"):
        assert context["moments_by_color"][color]
        assert all(move["color"] == color for move in context["moments_by_color"][color])


def test_actual_move_reply_and_alternative_replay_from_fen_before() -> None:
    pgn = "1. f3 e5 2. g4 Qh4# 0-1"
    evaluations = _evaluations(pgn)
    evaluations[2] = _error(
        evaluations[2], classification="blunder", played_line=["g4", "Qh4#"],
        best_move_san="e4", top_moves=[CandidateMove("e4", 0.0, ["e4", "Nf6"])],
        score_after=EngineScore(mate=-1),
    )
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert moment["move_number"] == 2
    assert moment["played_line"] == ["g4", "Qh4#"]
    assert moment["best_line"] == ["e4", "Nf6"]
    assert moment["score_after"] == EngineScore(mate=-1).to_json()
    assert moment["verification"] == "engine"
    for key in ("played_line", "best_line"):
        replay = chess.Board(moment["fen_before"])
        for san in moment[key]:
            move = replay.parse_san(san)
            assert replay.is_legal(move)
            replay.push(move)
    after = chess.Board(moment["fen_before"])
    after.push_san("g4")
    assert moment["fen_after"] == after.fen()
    assert any("black delivers checkmate" in fact for fact in moment["facts"])
    assert any("motive is not verified" in fact for fact in moment["facts"])
    assert not any("fork" in fact or "pin" in fact for fact in moment["facts"])


def test_captures_and_checks_derived_from_board_not_san_claims() -> None:
    pgn = "1. e4 d5 2. exd5 Qxd5 *"
    evaluations = _evaluations(pgn)
    evaluations[2] = _error(evaluations[2], played_line=["exd5", "Qxd5", "Bb5+"])
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert any("white captures a pawn on d5" in fact for fact in moment["facts"])
    assert any("black captures a pawn on d5" in fact for fact in moment["facts"])
    assert any("white gives check" in fact for fact in moment["facts"])


def test_invalid_and_wrong_anchor_lines_never_published() -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(
        evaluations[0], played_line=["d4", "d5"], best_move_san="d4",
        top_moves=[CandidateMove("d4", 0.0, ["d4", "e5", "Qh8"])],
    )
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert moment["played_line"] == ["e4"]
    assert moment["best_line"] == ["d4", "e5"]
    assert any("wrong anchor" in fact for fact in moment["facts"])
    assert any("invalid continuation" in fact for fact in moment["facts"])


def test_missing_score_and_reply_explicit_not_reconstructed_from_legacy_float() -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(
        evaluations[0], score_before=None, score_after=None, eval_after=9999.0,
        best_move_san="impossible", top_moves=[], played_line=[],
    )
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert moment["score_before"] is None
    assert moment["score_after"] is None
    assert moment["best_line"] == []
    assert moment["best_move_san"] == ""
    assert moment["played_line"] == ["e4"]
    assert any("legacy floats do not establish mate" in fact for fact in moment["facts"])
    assert any("No verified engine reply" in fact for fact in moment["facts"])


def test_null_reply_not_legal() -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(evaluations[0], played_line=["e4", "--", "Nf3"])
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert moment["played_line"] == ["e4"]
    assert any("illegal continuation" in fact for fact in moment["facts"])


def test_lines_capped_at_six_plies() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"
    evaluations = _evaluations(pgn)
    line = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"]
    evaluations[0] = _error(
        evaluations[0], played_line=line, top_moves=[CandidateMove("e4", 0.0, line)],
    )
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert moment["played_line"] == line[:6]
    assert moment["best_line"] == line[:6]


def test_en_passant_capture_fact() -> None:
    pgn = "1. e4 a6 2. e5 d5 3. exd6 *"
    evaluations = _evaluations(pgn)
    evaluations[4] = _error(evaluations[4])
    moment = build_review_context(pgn, evaluations, "white")["moments"][0]
    assert any("white captures a pawn on d5" in fact for fact in moment["facts"])


def _repetition_pgn(fullmoves: int) -> str:
    return " ".join(
        f"{i}. {'Nf3 Nf6' if i % 2 else 'Ng1 Ng8'}"
        for i in range(1, fullmoves + 1)
    ) + " *"


def test_repetitive_nearby_errors_not_all_selected_and_cap_five() -> None:
    pgn = _repetition_pgn(30)
    evaluations = [_error(ev) for ev in _evaluations(pgn)]
    moments = build_review_context(pgn, evaluations, "white")["moments"]
    assert len(moments) == 5
    indices = [moment["move_index"] for moment in moments]
    assert indices == sorted(indices)
    assert all(right - left >= 8 for left, right in pairwise(indices))
    short = "1. e4 e5 2. Nf3 Nc6 *"
    assert len(build_review_context(
        short, [_error(ev) for ev in _evaluations(short)], "white",
    )["moments"]) == 1


def test_mate_transition_selected_over_repeated_higher_cp_loss() -> None:
    pgn = _repetition_pgn(6)
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(evaluations[0], classification="blunder", centipawn_loss=1000)
    evaluations[2] = _error(
        evaluations[2], classification="blunder", centipawn_loss=200,
        score_after=EngineScore(mate=-2),
    )
    moments = build_review_context(pgn, evaluations, "white")["moments"]
    assert 2 in [moment["move_index"] for moment in moments]


def test_severity_not_only_centipawn_loss_controls_repeated_episode() -> None:
    pgn = _repetition_pgn(2)
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(evaluations[0], classification="inaccuracy", centipawn_loss=1000)
    evaluations[2] = _error(evaluations[2], classification="blunder", centipawn_loss=200)
    moments = build_review_context(pgn, evaluations, "white")["moments"]
    assert [moment["move_index"] for moment in moments] == [2]


def test_phase_boundary_keeps_distinct_lesson() -> None:
    pgn = _repetition_pgn(11)
    evaluations = _evaluations(pgn)
    evaluations[18] = _error(evaluations[18])
    evaluations[20] = _error(evaluations[20])
    moments = build_review_context(pgn, evaluations, "white")["moments"]
    assert [moment["move_index"] for moment in moments] == [18, 20]


def test_nearby_mistake_cannot_suppress_blunder() -> None:
    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 *"
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(
        evaluations[0], classification="blunder", played_line=["e4", "d5", "exd5"],
    )
    evaluations[4] = _error(evaluations[4], classification="blunder")
    evaluations[10] = _error(evaluations[10], classification="mistake")
    context = build_review_context(pgn, evaluations, "white")
    assert [moment["move_index"] for moment in context["moments"]] == [0, 4]
    assert context == build_review_context(pgn, evaluations, "white")


@pytest.mark.parametrize("color", ["white", "black"])
@pytest.mark.parametrize("transition", ["allow_mate", "lose_mate"])
def test_saturated_cp_best_still_reviews_adverse_typed_mate_transition(
    color: str, transition: str,
) -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    index = 0 if color == "white" else 1
    sign = 1 if color == "white" else -1
    if transition == "allow_mate":
        before, after = EngineScore(cp=-1500.0 * sign), EngineScore(mate=-sign)
        before_cp, after_cp, expected = -1500.0 * sign, -9999.0 * sign, "blunder"
    else:
        before, after = EngineScore(mate=sign), EngineScore(cp=1500.0 * sign)
        before_cp, after_cp, expected = 9999.0 * sign, 1500.0 * sign, "mistake"
    classification = classify_move(before_cp, after_cp, color == "white")
    assert classification == "best"
    evaluations[index] = replace(
        evaluations[index], eval_before=before_cp, eval_after=after_cp,
        score_before=before, score_after=after, classification=classification,
    )
    moment = build_review_context(pgn, evaluations, color)["moments"][0]
    assert moment["move_index"] == index
    assert moment["classification"] == expected
    assert moment["score_before"] == before.to_json()
    assert moment["score_after"] == after.to_json()
    assert evaluations[index].classification == "best"  # Pure builder does not mutate input.


@pytest.mark.parametrize("color", ["white", "black"])
@pytest.mark.parametrize("transition", ["gain_mate", "escape_mate", "keep_win", "keep_loss"])
def test_favorable_and_preserved_mate_transitions_are_not_review_errors(
    color: str, transition: str,
) -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    index = 0 if color == "white" else 1
    sign = 1 if color == "white" else -1
    transitions = {
        "gain_mate": (EngineScore(cp=0.0), EngineScore(mate=sign)),
        "escape_mate": (EngineScore(mate=-sign), EngineScore(cp=0.0)),
        "keep_win": (EngineScore(mate=sign), EngineScore(mate=8 * sign)),
        "keep_loss": (EngineScore(mate=-8 * sign), EngineScore(mate=-sign)),
    }
    before, after = transitions[transition]
    evaluations[index] = _error(
        evaluations[index], classification="blunder", score_before=before, score_after=after,
    )
    assert build_review_context(pgn, evaluations, color)["moments"] == []


@pytest.mark.parametrize("player_color", ["White", "", "both"])
def test_invalid_side_rejected(player_color: str) -> None:
    with pytest.raises(ValueError, match="player_color"):
        build_review_context("1. e4 *", _evaluations("1. e4 *"), player_color)


def test_mismatched_evaluations_rejected() -> None:
    pgn = "1. e4 e5 *"
    evaluations = _evaluations(pgn)
    with pytest.raises(ValueError, match="length"):
        build_review_context(pgn, evaluations[:1], "white")
    evaluations[1] = replace(evaluations[1], move_san="d5")
    with pytest.raises(ValueError, match="ply 1"):
        build_review_context(pgn, evaluations, "white")


@pytest.mark.parametrize("pgn", ["", "1. e4 e5 2. e5 *", "1. e4 *\n\n1. d4 *"])
def test_invalid_or_multiple_pgn_rejected(pgn: str) -> None:
    with pytest.raises(ValueError):
        build_review_context(pgn, [], "white")


def test_setup_fen_preserved_terminal_mate_is_not_an_error() -> None:
    pgn = (
        '[SetUp "1"]\n[FEN "7k/5Q2/6K1/8/8/8/8/8 w - - 0 42"]\n\n'
        '42. Qg7# 1-0'
    )
    evaluations = _evaluations(pgn)
    evaluations[0] = _error(
        evaluations[0], score_before=EngineScore(mate=1),
        score_after=EngineScore(mate=0, mate_winner="white"),
    )
    assert build_review_context(pgn, evaluations, "white")["moments"] == []
