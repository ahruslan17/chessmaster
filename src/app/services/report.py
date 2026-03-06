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
from app.services.llm_coach import LLMCoachService, PeriodReportInput

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PeriodAggregateStats:
    games_count: int
    avg_accuracy_white: float | None
    avg_accuracy_black: float | None
    overall_avg_accuracy: float | None
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
        current_stats = self._aggregate_period_stats(games_with_analyses)

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

        if not games_with_analyses:
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
            games=games_with_analyses,
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
        if not analysis:
            return ""

        parts = [f"{game.white_player} vs {game.black_player} - {game.result}"]
        if game.opening_name:
            eco = game.eco_code or "?"
            parts.append(f"Opening: {game.opening_name} ({eco})")

        for attr, prefix in [
            (analysis.summary, ""),
            (analysis.opening_assessment, "Opening: "),
            (analysis.middlegame_assessment, "Middlegame: "),
            (analysis.endgame_assessment, "Endgame: "),
        ]:
            if attr:
                parts.append(f"{prefix}{attr}" if prefix else attr)
        return "\n".join(parts)

    def _aggregate_period_stats(self, games: list[Game]) -> PeriodAggregateStats:
        """Build numeric aggregate stats used for deterministic comparison."""
        classification_counts: defaultdict[str, int] = defaultdict(int)
        accuracies_white: list[float] = []
        accuracies_black: list[float] = []

        for game in games:
            analysis = game.analysis
            if not analysis:
                continue
            if analysis.accuracy_white is not None:
                accuracies_white.append(analysis.accuracy_white)
            if analysis.accuracy_black is not None:
                accuracies_black.append(analysis.accuracy_black)
            for move in analysis.moves or []:
                if move.classification:
                    classification_counts[move.classification] += 1

        overall_values = accuracies_white + accuracies_black
        return PeriodAggregateStats(
            games_count=len(games),
            avg_accuracy_white=_avg(accuracies_white),
            avg_accuracy_black=_avg(accuracies_black),
            overall_avg_accuracy=_avg(overall_values),
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
        if aggregate.avg_accuracy_white is not None:
            stats["avg_accuracy_white"] = f"{aggregate.avg_accuracy_white:.1f}%"
        if aggregate.avg_accuracy_black is not None:
            stats["avg_accuracy_black"] = f"{aggregate.avg_accuracy_black:.1f}%"
        if aggregate.overall_avg_accuracy is not None:
            stats["overall_avg_accuracy"] = f"{aggregate.overall_avg_accuracy:.1f}%"

        return stats

    def _build_comparison_metrics(
        self,
        current: PeriodAggregateStats,
        previous: PeriodAggregateStats,
    ) -> dict[str, object]:
        """Build deterministic comparison metrics between two periods."""
        metrics: dict[str, object] = {
            "games": _delta_metric(current.games_count, previous.games_count),
            "previous_period_has_data": previous.games_count > 0,
        }

        if current.overall_avg_accuracy is not None and previous.overall_avg_accuracy is not None:
            metrics["overall_accuracy"] = _delta_metric(
                round(current.overall_avg_accuracy, 2),
                round(previous.overall_avg_accuracy, 2),
                precision=2,
            )
        if current.avg_accuracy_white is not None and previous.avg_accuracy_white is not None:
            metrics["white_accuracy"] = _delta_metric(
                round(current.avg_accuracy_white, 2),
                round(previous.avg_accuracy_white, 2),
                precision=2,
            )
        if current.avg_accuracy_black is not None and previous.avg_accuracy_black is not None:
            metrics["black_accuracy"] = _delta_metric(
                round(current.avg_accuracy_black, 2),
                round(previous.avg_accuracy_black, 2),
                precision=2,
            )

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
        if current.overall_avg_accuracy is not None and previous.overall_avg_accuracy is not None:
            delta_accuracy = current.overall_avg_accuracy - previous.overall_avg_accuracy
            if delta_accuracy >= 0:
                parts.append(
                    f"Средняя точность выросла на {delta_accuracy:.1f} п.п."
                )
            else:
                parts.append(
                    f"Средняя точность снизилась на {abs(delta_accuracy):.1f} п.п."
                )

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
                f"Количество грубых ошибок сократилось ({previous_errors} -> {current_errors})."
            )
        elif current_errors > previous_errors:
            parts.append(
                f"Количество грубых ошибок выросло ({previous_errors} -> {current_errors})."
            )
        else:
            parts.append(f"Количество грубых ошибок без изменений ({current_errors}).")

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
        game_summaries = [self._build_game_summary(game) for game in games if game.analysis]
        aggregate_stats = self._build_prompt_aggregate_stats(current_stats)

        return PeriodReportInput(
            period_type=period_type,
            period_start=str(period_start),
            period_end=str(period_end),
            games_count=len(games),
            game_summaries=game_summaries,
            aggregate_stats=aggregate_stats,
            previous_period_start=str(previous_period_start),
            previous_period_end=str(previous_period_end),
            previous_games_count=previous_stats.games_count,
            comparison_metrics=comparison_metrics,
        )


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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
