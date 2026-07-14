"""Fixture-path resolution for CLI / bench / replay.

Order: explicit argument > LAMPLIGHT_FIXTURES env > ./fixtures/ward_5day
relative to CWD > repo-root guess from the (editable-install) package path.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["find_fixtures", "repo_root_guess"]


def repo_root_guess() -> Path:
    # src/lamplight_memory/paths.py -> repo root (editable install / checkout)
    return Path(__file__).resolve().parents[2]


def find_fixtures(explicit: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("LAMPLIGHT_FIXTURES")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / "fixtures" / "ward_5day")
    candidates.append(repo_root_guess() / "fixtures" / "ward_5day")
    for c in candidates:
        if (c / "ground_truth.json").exists() or (c / "notes").exists():
            return c.resolve()
    raise FileNotFoundError(
        "could not locate fixtures/ward_5day — pass --fixtures, set "
        "LAMPLIGHT_FIXTURES, or run `python seed.py --regen` first"
    )
