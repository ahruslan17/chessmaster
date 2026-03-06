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
    "Отвечай только на русском языке. "
    "Верни только текст комментария (2-5 предложений), без JSON и без markdown.\n"
    "Для ходов с классификацией 'theory': объясни идею хода, не предлагай альтернативы. "
    "Для excellent/best/good: краткая позитивная оценка. "
    "Для inaccuracy/mistake/blunder: объясни ошибку и лучшую альтернативу. "
    "Используй и линии движка, и фактическое продолжение партии, чтобы показать долгосрочные последствия."
)

MOVE_COMMENTARY_SYSTEM = (
    "Ты опытный шахматный тренер, который делает походовый разбор партии. "
    "Аудитория: клубный игрок уровня Elo 1200-1800.\n\n"
    "Отвечай только на русском языке.\n\n"
    "Правила:\n"
    '- Для "theory" ходов: объясни, почему ход играется и какие идеи поддерживает. Не предлагай альтернативы.\n'
    '- Для "excellent" ходов: 1 короткое предложение о почти идеальном ходе.\n'
    '- Для "best" ходов: 1 короткое предложение с позитивной оценкой.\n'
    '- Для "good" ходов: 1-2 предложения о практической уместности.\n'
    '- Для "inaccuracy" ходов: 2-3 предложения о неточности и лучшей альтернативе.\n'
    '- Для "mistake" ходов: 3-4 предложения с разбором ошибки и последствий.\n'
    '- Для "blunder" ходов: 4-5 предложений с подробным разбором критической ошибки.\n\n'
    "Используй стандартную алгебраическую нотацию. "
    "Сравнивай PV движка и реальное продолжение партии.\n\n"
    "Ты обязан вернуть только JSON-объект в точном формате (без markdown и лишнего текста):\n"
    "{\n"
    '  "comments": [\n'
    '    {"move_index": 0, "comment": "Комментарий тренера."},\n'
    "    ...\n"
    "  ]\n"
    "}"
)

GAME_SUMMARY_SYSTEM = (
    "Ты опытный шахматный тренер, который пишет послематчевый разбор. "
    "Нужно дать честную, конкретную и практичную обратную связь.\n\n"
    "Отвечай только на русском языке.\n\n"
    "Ты обязан вернуть только JSON-объект в точном формате (без markdown и лишнего текста):\n"
    "{\n"
    '  "summary": "Общий итог партии (2-4 предложения).",\n'
    '  "opening_assessment": "Оценка дебюта (1-3 предложения).",\n'
    '  "middlegame_assessment": "Оценка миттельшпиля (1-3 предложения).",\n'
    '  "endgame_assessment": "Оценка эндшпиля (1-3 предложения) или отметка, что до него партия не дошла.",\n'
    '  "key_moments": [\n'
    '    {"move": "15...Bxd5??", "description": "Почему это переломный момент."}\n'
    "  ],\n"
    '  "coach_feedback": {\n'
    '    "pluses": ["Что получилось хорошо"],\n'
    '    "minuses": ["Ключевые проблемы"],\n'
    '    "focus_points": ["На чем сфокусироваться в ближайших партиях"],\n'
    '    "training_tasks": ["Конкретные задания: теория, задачи, тип позиций"]\n'
    "  }\n"
    "}"
)

PERIOD_REPORT_SYSTEM = (
    "Ты шахматный тренер, который пишет отчёт о прогрессе игрока за период. "
    "Нужно дать практичный план улучшения, а не общие фразы.\n\n"
    "Отвечай только на русском языке.\n\n"
    "Ты обязан вернуть только JSON-объект в точном формате (без markdown и лишнего текста):\n"
    "{\n"
    '  "recommendations": "Подробные рекомендации (1-3 абзаца).",\n'
    '  "comparison_summary": "Сравнение с предыдущим периодом: что стало лучше/хуже и почему.",\n'
    '  "weakness_patterns": [\n'
    '    {"pattern": "Короткое название", "description": "Подробное описание", "frequency": "например, 4 из 10 партий"}\n'
    "  ],\n"
    '  "strength_patterns": [\n'
    '    {"pattern": "Короткое название", "description": "Подробное описание", "frequency": "например, 7 из 10 партий"}\n'
    "  ],\n"
    '  "coach_feedback": {\n'
    '    "pluses": ["Главные улучшения"],\n'
    '    "minuses": ["Главные просадки"],\n'
    '    "action_items": ["Конкретные действия на следующий период"]\n'
    "  }\n"
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
    """Build chat messages for per-move commentary generation."""
    user_parts: list[str] = [
        "Проанализируй следующие ходы и дай комментарий по каждому.",
        "",
    ]
    for move in moves:
        user_parts.append(_format_move_context(move))
        user_parts.append("")

    return [
        {"role": "system", "content": MOVE_COMMENTARY_SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def build_game_summary_messages(
    context: GameSummaryInput,
) -> list[dict[str, str]]:
    """Build chat messages for game summary generation."""
    lines: list[str] = [
        f"Партия: {context.white_player} vs {context.black_player}",
        f"Результат: {context.result}",
    ]
    if context.opening_name:
        eco = context.eco_code or "?"
        lines.append(f"Дебют: {context.opening_name} ({eco})")
    lines.append(f"Всего полуходов: {context.total_moves}")
    lines.append(
        f"Точность - Белые: {context.accuracy_white:.1f}%, Черные: {context.accuracy_black:.1f}%"
    )
    lines.append("")
    lines.append("Распределение классификаций ходов:")
    for classification, count in sorted(context.classification_counts.items()):
        lines.append(f"  {classification}: {count}")

    if context.key_moments:
        lines.append("")
        lines.append("Ключевые моменты (неточности, ошибки, зевки):")
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
        f"Тип периода: {context.period_type}",
        f"Текущий период: {context.period_start} - {context.period_end}",
        f"Проанализировано партий: {context.games_count}",
        "",
    ]

    if context.previous_period_start and context.previous_period_end:
        lines.extend(
            [
                f"Предыдущий период: {context.previous_period_start} - {context.previous_period_end}",
                f"Партий в предыдущем периоде: {context.previous_games_count}",
                "",
            ]
        )

    if context.aggregate_stats:
        lines.append("Агрегированная статистика текущего периода:")
        for key, value in context.aggregate_stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    if context.comparison_metrics:
        lines.append("Метрики сравнения с предыдущим периодом:")
        for key, value in context.comparison_metrics.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    lines.append("Индивидуальные краткие разборы партий:")
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
