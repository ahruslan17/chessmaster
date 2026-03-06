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
    "Ты опытный шахматный тренер, который делает походовый разбор партии. "
    "Аудитория: клубный игрок уровня Elo 1200-1800.\n\n"
    "Отвечай ТОЛЬКО на русском языке. "
    "Верни ТОЛЬКО текст комментария (2-5 предложений), без JSON и без markdown.\n"
    "Для ходов с классификацией 'theory': объясни идею хода, "
    "не предлагай альтернативы. "
    "Для excellent/best/good: краткая позитивная оценка. "
    "Для inaccuracy/mistake/blunder: объясни ошибку и лучшую альтернативу. "
    "Используй и линии движка, и фактическое продолжение партии, "
    "чтобы показать долгосрочные последствия.\n"
)

MOVE_COMMENTARY_SYSTEM = (
    "Ты опытный шахматный тренер, который делает походовый разбор партии. "
    "Аудитория: клубный игрок уровня Elo 1200-1800.\n\n"
    "Отвечай ТОЛЬКО на русском языке.\n\n"
    "Правила:\n"
    '- Для "theory" ходов: объясни, почему ход играется и какие идеи поддерживает. '
    "Не предлагай альтернативы.\n"
    '- Для "excellent" ходов: 1 короткое предложение о почти идеальном ходе.\n'
    '- Для "best" ходов: 1 короткое предложение с позитивной оценкой.\n'
    '- Для "good" ходов: 1-2 предложения о практической уместности.\n'
    '- Для "inaccuracy" ходов: 2-3 предложения о неточности и лучшей альтернативе.\n'
    '- Для "mistake" ходов: 3-4 предложения с разбором ошибки и последствий.\n'
    '- Для "blunder" ходов: 4-5 предложений с подробным разбором критической ошибки.\n\n'
    "Используй стандартную алгебраическую нотацию. Сравнивай PV движка "
    "и реальное продолжение партии, чтобы объяснить и ближайшие, и долгосрочные "
    "последствия хода.\n\n"
    "Ты ОБЯЗАН вернуть ТОЛЬКО JSON-объект в точном формате "
    "(без markdown и лишнего текста):\n"
    "{\n"
    '  "comments": [\n'
    '    {"move_index": 0, "comment": "Комментарий тренера."},\n'
    "    ...\n"
    "  ]\n"
    "}"
)

GAME_SUMMARY_SYSTEM = (
    "Ты опытный шахматный тренер, который пишет послематчевый разбор. "
    "Оцени общее качество игры, разбор по стадиям партии и ключевые переломные "
    "моменты.\n\n"
    "Отвечай ТОЛЬКО на русском языке.\n\n"
    "Ты ОБЯЗАН вернуть ТОЛЬКО JSON-объект в точном формате "
    "(без markdown и лишнего текста):\n"
    "{\n"
    '  "summary": "Общий итог партии (2-4 предложения).",\n'
    '  "opening_assessment": "Оценка дебюта (1-3 предложения).",\n'
    '  "middlegame_assessment": "Оценка миттельшпиля (1-3 предложения).",\n'
    '  "endgame_assessment": "Оценка эндшпиля (1-3 предложения) '
    'или отметка, что до него партия не дошла.",\n'
    '  "key_moments": [\n'
    '    {"move": "15...Bxd5??", "description": "Почему это был переломный момент."}\n'
    "  ]\n"
    "}"
)

PERIOD_REPORT_SYSTEM = (
    "Ты шахматный тренер, который пишет отчет о прогрессе по нескольким партиям "
    "за выбранный период. Определи повторяющиеся паттерны (сильные и слабые стороны) "
    "и дай конкретные рекомендации.\n\n"
    "Отвечай ТОЛЬКО на русском языке.\n\n"
    "Ты ОБЯЗАН вернуть ТОЛЬКО JSON-объект в точном формате "
    "(без markdown и лишнего текста):\n"
    "{\n"
    '  "recommendations": "Подробные рекомендации (1-3 абзаца).",\n'
    '  "weakness_patterns": [\n'
    '    {"pattern": "Короткое название", "description": "Подробное описание", '
    '"frequency": "например, 4 из 10 партий"}\n'
    "  ],\n"
    '  "strength_patterns": [\n'
    '    {"pattern": "Короткое название", "description": "Подробное описание", '
    '"frequency": "например, 7 из 10 партий"}\n'
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
        "Проанализируй следующие ходы и дай комментарий по каждому.",
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
        f"Accuracy - White: {context.accuracy_white:.1f}%, Black: {context.accuracy_black:.1f}%"
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
