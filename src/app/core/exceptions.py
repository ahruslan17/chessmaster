"""Application-specific exceptions for structured error handling."""

from __future__ import annotations


class AppError(Exception):
    """Base exception for application errors.

    All custom exceptions should inherit from this to allow
    centralized handling and consistent API error responses.
    """

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


class GameNotFoundError(AppError):
    """Raised when a requested game does not exist."""


class AnalysisNotFoundError(AppError):
    """Raised when analysis for a game does not exist."""


class PGNParseError(AppError):
    """Raised when PGN text cannot be parsed into valid games."""


class AnalysisError(AppError):
    """Raised when game analysis (Stockfish or pipeline) fails."""


class ReportNotFoundError(AppError):
    """Raised when a requested period report does not exist."""
