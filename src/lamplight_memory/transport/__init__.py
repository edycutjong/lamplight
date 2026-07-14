"""Transport selection: fake (offline, default) or live (Qwen Cloud)."""

from __future__ import annotations

from pathlib import Path

from .base import Transport
from .fake import FakeQwen

__all__ = ["Transport", "FakeQwen", "get_transport"]


def get_transport(
    name: str,
    fixtures_root: str | Path | None = None,
    extraction_map: dict | None = None,
) -> Transport:
    if name == "fake":
        return FakeQwen(fixtures_root=fixtures_root, extraction_map=extraction_map)
    if name == "live":
        from .live import LiveQwen  # imports openai lazily

        return LiveQwen()
    raise ValueError(f"unknown transport: {name!r} (expected 'fake' or 'live')")
