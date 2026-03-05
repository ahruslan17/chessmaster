from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.llm_coach import (
        GameSummaryInput,
        MoveCommentaryInput,
        PeriodReportInput,
    )

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SINGLE_MOVE_COMMENTARY_SYSTEM = (
    "You are an experienced chess coach providing move-by-move analysis. "
    "Your audience is an intermediate club player (Elo 1200-1800).\n\n"
    "Respond with ONLY the coaching comment in plain text (2-5 sentences). "
    "No JSON, no markdown fences, no preamble. "
    "For 'theory' moves (opening book): explain why this move is played and what "
    "it aims to achieve; do NOT suggest a best move or alternative. "
    "For best/good moves: brief positive reinforcement. "
    "For inaccuracies/mistakes/blunders: explain the error and better alternative. "
    "Use both engine lines and the real game continuation to explain long-term impact.\n"
)

MOVE_COMMENTARY_SYSTEM = (
    "You are an experienced chess coach providing move-by-move analysis. "
    "Your audience is an intermediate club player (Elo 1200-1800) who wants to "
    "understand the reasoning behind good and bad moves.\n\n"
    "Guidelines:\n"
    '- For "theory" moves (opening book): explain why this move is played, what '
    "ideas it supports, and what it aims to achieve. Do NOT suggest a best move "
    "or alternative — this is known theory. Focus on the rationale and benefits.\n"
    '- For "best" moves: 1 brief sentence of positive reinforcement.\n'
    '- For "good" moves: 1-2 sentences noting it is a solid choice.\n'
    '- For "inaccuracy" moves: 2-3 sentences explaining the slight inaccuracy '
    "and the better alternative.\n"
    '- For "mistake" moves: 3-4 sentences with a clear explanation of the error, '
    "the better move, and the resulting consequences.\n"
    '- For "blunder" moves: 4-5 sentences with a detailed explanation of the '
    "critical error, the best move, and how the position changes.\n\n"
    "Use standard algebraic notation. Reference engine-suggested continuations "
    "when they clarify the point. Compare the engine PV with the real game "
    "continuation to explain both immediate and long-term consequences of the move. "
    "Be encouraging but honest.\n\n"
    "You MUST respond with ONLY a JSON object in this exact format "
    "(no markdown fences, no extra text):\n"
    "{\n"
    '  "comments": [\n'
    '    {"move_index": 0, "comment": "Your coaching comment here."},\n'
    "    ...\n"
    "  ]\n"
    "}"
)

GAME_SUMMARY_SYSTEM = (
    "You are an experienced chess coach writing a post-game analysis. "
    "Analyze the overall quality of play, assess each game phase, and highlight "
    "the key turning points. Your audience is the same player whose game you are "
    "reviewing.\n\n"
    "You MUST respond with ONLY a JSON object in this exact format "
    "(no markdown fences, no extra text):\n"
    "{\n"
    '  "summary": "2-4 sentence overall game summary.",\n'
    '  "opening_assessment": "1-3 sentences on the opening phase.",\n'
    '  "middlegame_assessment": "1-3 sentences on the middlegame.",\n'
    '  "endgame_assessment": "1-3 sentences on the endgame '
    '(or note if the game ended before this phase).",\n'
    '  "key_moments": [\n'
    '    {"move": "15...Bxd5??", "description": "Why this was a turning point."}\n'
    "  ]\n"
    "}"
)

PERIOD_REPORT_SYSTEM = (
    "You are a chess coach writing a progress report covering multiple games "
    "played over a time period. Identify recurring patterns (both strengths and "
    "weaknesses), and provide actionable recommendations for improvement. "
    "Be specific, constructive, and encouraging.\n\n"
    "You MUST respond with ONLY a JSON object in this exact format "
    "(no markdown fences, no extra text):\n"
    "{\n"
    '  "recommendations": "Detailed coaching recommendations (1-3 paragraphs).",\n'
    '  "weakness_patterns": [\n'
    '    {"pattern": "Short name", "description": "Detailed description", '
    '"frequency": "e.g. 4 out of 10 games"}\n'
    "  ],\n"
    '  "strength_patterns": [\n'
    '    {"pattern": "Short name", "description": "Detailed description", '
    '"frequency": "e.g. 7 out of 10 games"}\n'
    "  ]\n"
    "}"
)


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------


def build_single_move_commentary_messages(
    move: MoveCommentaryInput,
) -> list[dict[str, str]]:
    """Build messages for streaming single-move commentary (plain text, no JSON)."""
    return [
        {"role": "system", "content": SINGLE_MOVE_COMMENTARY_SYSTEM},
        {"role": "user", "content": _format_move_context(move)},
    ]


def build_move_commentary_messages(
    moves: list[MoveCommentaryInput],
) -> list[dict[str, str]]:
    """Build chat messages for per-move commentary generation.

    Returns a list of ``{"role": ..., "content": ...}`` dicts ready for
    ``litellm.acompletion``.
    """
    user_parts: list[str] = [
        "Analyze the following moves and provide coaching commentary for each.",
        "",
    ]
    for move in moves:
        user_parts.append(_format_move_context(move))
        user_parts.append("")  # blank line between moves

    return [
        {"role": "system", "content": MOVE_COMMENTARY_SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def build_game_summary_messages(
    context: GameSummaryInput,
) -> list[dict[str, str]]:
    """Build chat messages for game summary generation."""
    lines: list[str] = [
        f"Game: {context.white_player} vs {context.black_player}",
        f"Result: {context.result}",
    ]
    if context.opening_name:
        eco = context.eco_code or "?"
        lines.append(f"Opening: {context.opening_name} ({eco})")
    lines.append(f"Total half-moves: {context.total_moves}")
    lines.append(
        f"Accuracy — White: {context.accuracy_white:.1f}%, Black: {context.accuracy_black:.1f}%"
    )
    lines.append("")
    lines.append("Move classification distribution:")
    for classification, count in sorted(context.classification_counts.items()):
        lines.append(f"  {classification}: {count}")

    if context.key_moments:
        lines.append("")
        lines.append("Notable moments (inaccuracies, mistakes, blunders):")
        for moment in context.key_moments:
            lines.append(_format_move_context(moment))
            lines.append("")

    return [
        {"role": "system", "content": GAME_SUMMARY_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def build_period_report_messages(
    context: PeriodReportInput,
) -> list[dict[str, str]]:
    """Build chat messages for period report generation."""
    lines: list[str] = [
        f"Period: {context.period_start} to {context.period_end}",
        f"Games analyzed: {context.games_count}",
        "",
    ]
    if context.aggregate_stats:
        lines.append("Aggregate statistics:")
        for key, value in context.aggregate_stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    lines.append("Individual game summaries:")
    for idx, summary in enumerate(context.game_summaries, 1):
        lines.append(f"\n--- Game {idx} ---")
        lines.append(summary)

    return [
        {"role": "system", "content": PERIOD_REPORT_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOP_MOVES_IN_PROMPT = 3
_PV_MOVES_IN_PROMPT = 10
_NEXT_GAME_MOVES_IN_PROMPT = 10


def _format_move_context(move: MoveCommentaryInput) -> str:
    """Format a single move's context into readable text for the LLM prompt."""
    color_sep = "." if move.color == "white" else "..."
    move_label = f"{move.move_number}{color_sep}{move.move_san}"

    lines: list[str] = [
        f"[Move {move.move_index}] {move_label} "
        f"({move.classification}, cp_loss={move.centipawn_loss:.0f})",
        f"  FEN: {move.fen_before}",
        f"  Played: {move.move_san} | Best: {move.best_move_san}",
        f"  Eval: {move.eval_before:+.0f} -> {move.eval_after:+.0f} cp",
    ]

    if move.top_moves:
        lines.append("  Engine lines:")
        for candidate in move.top_moves[:_TOP_MOVES_IN_PROMPT]:
            pv_san = candidate.get("pv_san", [])
            pv_str = " ".join(pv_san[:_PV_MOVES_IN_PROMPT])
            eval_cp = candidate.get("eval_cp", 0)
            move_san = candidate.get("move_san", "?")
            lines.append(f"    {move_san} ({eval_cp:+.0f} cp): {pv_str}")

    if move.next_game_moves:
        continuation = " ".join(move.next_game_moves[:_NEXT_GAME_MOVES_IN_PROMPT])
    else:
        continuation = "<none>"
    lines.append(
        "  Actual game continuation "
        f"(next {_NEXT_GAME_MOVES_IN_PROMPT} half-moves): {continuation}"
    )

    return "\n".join(lines)
