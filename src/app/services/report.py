from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.period_report import PeriodReport
from app.services.llm_coach import LLMCoachService, PeriodReportInput

logger = logging.getLogger(__name__)


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
        """Generate a coaching report for the given period.

        Fetches games with completed analyses, aggregates statistics,
        calls the LLM for recommendations and pattern detection,
        and persists the report.
        """
        games_with_analyses = await self._fetch_games_with_analyses(period_start, period_end)

        game_ids = [str(g.id) for g in games_with_analyses]

        report = PeriodReport(
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            game_ids=game_ids,
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
            period_start=period_start,
            period_end=period_end,
            games=games_with_analyses,
        )

        try:
            result = await self._llm.generate_period_report(context)
            report.recommendations = result.recommendations
            report.weakness_patterns = result.weakness_patterns
            report.strength_patterns = result.strength_patterns
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
            .options(
                selectinload(Game.analysis).selectinload(GameAnalysis.moves),
            )
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

    def _build_aggregate_stats(
        self,
        classification_counts: dict[str, int],
        accuracies_white: list[float],
        accuracies_black: list[float],
    ) -> dict[str, object]:
        """Build aggregate statistics for the LLM prompt."""
        stats: dict[str, object] = {}
        if classification_counts:
            stats["classification_counts"] = ", ".join(
                f"{k}: {v}" for k, v in sorted(classification_counts.items())
            )
        if accuracies_white:
            stats["avg_accuracy_white"] = f"{sum(accuracies_white) / len(accuracies_white):.1f}%"
        if accuracies_black:
            stats["avg_accuracy_black"] = f"{sum(accuracies_black) / len(accuracies_black):.1f}%"
        if accuracies_white or accuracies_black:
            all_acc = accuracies_white + accuracies_black
            stats["overall_avg_accuracy"] = f"{sum(all_acc) / len(all_acc):.1f}%"
        return stats

    def _build_period_report_input(
        self,
        period_start: date,
        period_end: date,
        games: list[Game],
    ) -> PeriodReportInput:
        """Build the input context for LLM period report generation."""
        game_summaries: list[str] = []
        classification_counts: defaultdict[str, int] = defaultdict(int)
        accuracies_white: list[float] = []
        accuracies_black: list[float] = []

        for game in games:
            analysis = game.analysis
            if not analysis:
                continue
            game_summaries.append(self._build_game_summary(game))
            if analysis.accuracy_white is not None:
                accuracies_white.append(analysis.accuracy_white)
            if analysis.accuracy_black is not None:
                accuracies_black.append(analysis.accuracy_black)
            for move in analysis.moves or []:
                if move.classification:
                    classification_counts[move.classification] += 1

        aggregate_stats = self._build_aggregate_stats(
            dict(classification_counts), accuracies_white, accuracies_black
        )

        return PeriodReportInput(
            period_start=str(period_start),
            period_end=str(period_end),
            games_count=len(games),
            game_summaries=game_summaries,
            aggregate_stats=aggregate_stats,
        )
