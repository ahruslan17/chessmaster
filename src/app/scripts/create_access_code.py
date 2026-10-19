from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta

from app.core.database import async_session_factory, engine
from app.services.access import AccessCodeError, create_access_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one Chess Master access code")
    parser.add_argument("--valid-for-hours", type=float, default=24)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        async with async_session_factory() as session:
            code = await create_access_code(session, timedelta(hours=args.valid_for_hours))
    except AccessCodeError as exc:
        sys.stderr.write(f"Ошибка: {exc}\n")
        return 2
    finally:
        await engine.dispose()
    sys.stdout.write(f"{code}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
