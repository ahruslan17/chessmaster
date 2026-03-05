from __future__ import annotations

import pytest

# Shared pytest fixtures.
# Async DB session and test client fixtures will be added in Phase 4/7.

SAMPLE_PGN_SINGLE = """\
[Event "Test Game"]
[Site "Internet"]
[Date "2024.06.15"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]
[ECO "C50"]
[Opening "Italian Game"]
[TimeControl "600+5"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. d3 Be7 5. O-O O-O 1-0
"""

SAMPLE_PGN_MULTI = """\
[Event "Game 1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]
[Date "2024.01.10"]

1. e4 e5 2. Nf3 Nc6 1-0

[Event "Game 2"]
[White "Charlie"]
[Black "Dana"]
[Result "0-1"]
[Date "2024.02.20"]

1. d4 d5 2. c4 e6 0-1
"""

SAMPLE_PGN_MINIMAL = """\
[Result "*"]

1. e4 e5 *
"""


@pytest.fixture()
def sample_pgn_single() -> str:
    return SAMPLE_PGN_SINGLE


@pytest.fixture()
def sample_pgn_multi() -> str:
    return SAMPLE_PGN_MULTI


@pytest.fixture()
def sample_pgn_minimal() -> str:
    return SAMPLE_PGN_MINIMAL
