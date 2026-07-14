"""Transport abstraction: one interface, two implementations.

- FakeQwen  — deterministic, offline, zero keys. Hash-based embeddings,
              keyword-overlap rerank, fixture-backed extraction. The entire
              test suite, bench, and judge replay run on it.
- LiveQwen  — Qwen Cloud via the OpenAI-compatible endpoint
              (qwen3.7-plus extraction+brief, text-embedding-v4,
              qwen3-rerank, fun-asr voice ingest).

The engine never knows which one it holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import Episode

__all__ = ["Transport"]


class Transport(ABC):
    name: str = "base"
    dim: int = 256

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """L2-normalized embedding per text (dimension = self.dim)."""

    @abstractmethod
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Relevance score in [0, 1] per document, aligned by index."""

    @abstractmethod
    def extract(self, note_text: str, bed: int, shift: int) -> list[Episode]:
        """Structured episodes for one shift note."""

    def brief_prose(self, context: dict) -> dict | None:
        """Optional LLM SBAR prose. None -> deterministic template is used.
        Citations are attached mechanically either way (never model-invented)."""
        return None

    def transcribe(self, audio_path: str) -> str:
        """Voice-note ingest (fun-asr). Live-only."""
        raise NotImplementedError(f"{self.name} transport does not support ASR")
