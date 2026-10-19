from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.period_report import PeriodReport
from app.schemas.report import REPORT_CONTENT_VERSION
from app.services.llm_coach import LLMCoachService, PeriodReportInput

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PeriodAggregateStats:
    games_count: int
    classification_counts: dict[str, int]


class ReportService:
    """Generates period coaching reports with aggregation and LLM recommendations."""

    def __init__(
        self,
        session: AsyncSession,
        llm_coach: LLMCoachService | None = None,
    ) -> None:
        self._session = session
        self._llm = llm_coach or LLMCoachService()

    async def generate_report(
        self,
        period_start: date,
        period_end: date,
        period_type: str,
    ) -> PeriodReport:
        """Generate a coaching report for the given period."""
        games_with_analyses = await self._fetch_games_with_analyses(period_start, period_end)
        personal_games = [g for g in games_with_analyses if g.player_color in ("white", "black")]
        current_stats = self._aggregate_period_stats(personal_games)

        previous_period_start, previous_period_end = _build_previous_period(
            period_start, period_end
        )
        previous_games = await self._fetch_games_with_analyses(
            previous_period_start,
            previous_period_end,
        )
        previous_stats = self._aggregate_period_stats(previous_games)
        comparison_metrics = self._build_comparison_metrics(current_stats, previous_stats)
        fallback_comparison_summary = self._build_comparison_summary(
            current_stats,
            previous_stats,
        )
        omitted_count = len(games_with_analyses) - len(personal_games)
        if omitted_count:
            fallback_comparison_summary += (
                " Партий без выбранной стороны исключено из персонального отчёта: "
                f"{omitted_count}."
            )

        game_ids = [str(game.id) for game in games_with_analyses]
        report = PeriodReport(
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            game_ids=game_ids,
            comparison_metrics=comparison_metrics or None,
            comparison_summary=fallback_comparison_summary,
        )
        self._session.add(report)
        await self._session.flush()

        if not personal_games:
            logger.info(
                "No analyzed games in period %s-%s; report created without LLM",
                period_start,
                period_end,
            )
            return report

        context = self._build_period_report_input(
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            games=personal_games,
            current_stats=current_stats,
            previous_period_start=previous_period_start,
            previous_period_end=previous_period_end,
            previous_stats=previous_stats,
            comparison_metrics=comparison_metrics,
        )

        try:
            result = await self._llm.generate_period_report(context)
            report.recommendations = result.recommendations or None
            report.weakness_patterns = result.weakness_patterns or None
            report.strength_patterns = result.strength_patterns or None
            report.coach_feedback = result.coach_feedback or None
            if result.comparison_summary:
                report.comparison_summary = result.comparison_summary
                if omitted_count:
                    report.comparison_summary += (
                        " Партий без выбранной стороны исключено из персонального отчёта: "
                        f"{omitted_count}."
                    )
        except Exception as exc:
            logger.warning(
                "LLM period report generation failed: %s; saving report without it",
                exc,
            )

        return report

    async def _fetch_games_with_analyses(
        self,
        period_start: date,
        period_end: date,
    ) -> list[Game]:
        """Fetch games played in the period that have completed analyses."""
        stmt = (
            select(Game)
            .join(Game.analysis)
            .where(
                Game.played_at >= period_start,
                Game.played_at <= period_end,
                GameAnalysis.status == "done",
            )
            .options(selectinload(Game.analysis).selectinload(GameAnalysis.moves))
            .order_by(Game.played_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    def _build_game_summary(self, game: Game) -> str:
        """Build a text summary for a single game."""
        analysis = game.analysis
        if not analysis or game.player_color not in ("white", "black"):
            return ""

        parts = [f"{game.white_player} vs {game.black_player} - {game.result}"]
        parts.append(f"Student side: {game.player_color}; counts include only this side's moves.")
        if game.opening_name:
            eco = game.eco_code or "?"
            parts.append(f"Opening: {game.opening_name} ({eco})")

        # Legacy free-form summaries may contain retired, untrustworthy percentages.
        # Use stored engine classifications, not old generated prose, as report facts.
        counts: defaultdict[str, int] = defaultdict(int)
        for move in analysis.moves or []:
            if move.color == game.player_color and move.classification:
                counts[move.classification] += 1
        parts.append(f"Move classifications: {dict(sorted(counts.items()))}")
        return "\n".join(parts)

    def _aggregate_period_stats(self, games: list[Game]) -> PeriodAggregateStats:
        """Build numeric aggregate stats used for deterministic comparison."""
        classification_counts: defaultdict[str, int] = defaultdict(int)
        games_count = 0

        for game in games:
            analysis = game.analysis
            if not analysis or game.player_color not in ("white", "black"):
                continue
            games_count += 1
            for move in analysis.moves or []:
                if move.color == game.player_color and move.classification:
                    classification_counts[move.classification] += 1

        return PeriodAggregateStats(
            games_count=games_count,
            classification_counts=dict(classification_counts),
        )

    def _build_prompt_aggregate_stats(
        self,
        aggregate: PeriodAggregateStats,
    ) -> dict[str, object]:
        """Build aggregate statistics formatted for LLM prompts."""
        stats: dict[str, object] = {"games_count": aggregate.games_count}

        if aggregate.classification_counts:
            stats["classification_counts"] = ", ".join(
                f"{key}: {value}"
                for key, value in sorted(aggregate.classification_counts.items())
            )

        return stats

    def _build_comparison_metrics(
        self,
        current: PeriodAggregateStats,
        previous: PeriodAggregateStats,
    ) -> dict[str, object]:
        """Build deterministic comparison metrics between two periods."""
        metrics: dict[str, object] = {
            "content_version": REPORT_CONTENT_VERSION,
            "games": _delta_metric(current.games_count, previous.games_count),
            "previous_period_has_data": previous.games_count > 0,
        }

        tracked = ("blunder", "mistake", "inaccuracy", "best", "excellent", "good", "theory")
        for key in tracked:
            current_value = current.classification_counts.get(key, 0)
            previous_value = previous.classification_counts.get(key, 0)
            if current_value or previous_value:
                metrics[f"{key}_moves"] = _delta_metric(current_value, previous_value)

        return metrics

    def _build_comparison_summary(
        self,
        current: PeriodAggregateStats,
        previous: PeriodAggregateStats,
    ) -> str:
        """Build a fallback comparison summary without LLM."""
        if previous.games_count == 0:
            return (
                "Для предыдущего периода нет достаточных данных, поэтому сравнение ограничено "
                "текущей выборкой."
            )

        parts: list[str] = []
        current_errors = sum(
            current.classification_counts.get(name, 0)
            for name in ("inaccuracy", "mistake", "blunder")
        )
        previous_errors = sum(
            previous.classification_counts.get(name, 0)
            for name in ("inaccuracy", "mistake", "blunder")
        )
        if current_errors < previous_errors:
            parts.append(
                "Количество отмеченных ошибок сократилось "
                f"({previous_errors} -> {current_errors})."
            )
        elif current_errors > previous_errors:
            parts.append(
                f"Количество отмеченных ошибок выросло ({previous_errors} -> {current_errors})."
            )
        else:
            parts.append(f"Количество отмеченных ошибок без изменений ({current_errors}).")

        parts.append(
            "Размеры выборок могут различаться; эти количества не доказывают рост навыка."
        )

        return " ".join(parts)

    def _build_period_report_input(
        self,
        period_type: str,
        period_start: date,
        period_end: date,
        games: list[Game],
        current_stats: PeriodAggregateStats,
        previous_period_start: date,
        previous_period_end: date,
        previous_stats: PeriodAggregateStats,
        comparison_metrics: dict[str, object],
    ) -> PeriodReportInput:
        """Build the input context for LLM period report generation."""
        game_summaries = [
            summary for game in games if (summary := self._build_game_summary(game))
        ]
        aggregate_stats = self._build_prompt_aggregate_stats(current_stats)

        return PeriodReportInput(
            period_type=period_type,
            period_start=str(period_start),
            period_end=str(period_end),
            games_count=current_stats.games_count,
            game_summaries=game_summaries,
            aggregate_stats=aggregate_stats,
            previous_period_start=str(previous_period_start),
            previous_period_end=str(previous_period_end),
            previous_games_count=previous_stats.games_count,
            comparison_metrics=comparison_metrics,
        )


def _build_previous_period(period_start: date, period_end: date) -> tuple[date, date]:
    span = (period_end - period_start).days + 1
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    return previous_start, previous_end


def _delta_metric(
    current: float | int,
    previous: float | int,
    *,
    precision: int = 1,
) -> dict[str, float | int | None]:
    delta = current - previous
    result: dict[str, float | int | None] = {
        "current": current,
        "previous": previous,
        "delta": round(delta, precision) if isinstance(delta, float) else delta,
    }
    if previous == 0:
        result["delta_percent"] = None
    else:
        percent = (delta / abs(previous)) * 100
        result["delta_percent"] = round(percent, 1)
    return result
