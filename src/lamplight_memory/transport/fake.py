"""FakeQwen — deterministic offline transport (zero keys, zero sockets).

HONEST DISCLOSURE (also in README): offline bench numbers use these fake
embeddings, not text-embedding-v4. The fake embedding is a *surface-form*
bag-of-tokens hash: two phrasings that share no vocabulary ("erythema
forearm" vs "red patches" vs "rash") are near-orthogonal vectors. That is
exactly the failure mode of naive RAG that Lamplight's structural machinery
(entity consolidation, decay classes, criticality weighting) exists to fix —
so the offline bench separates the two systems for *architectural* reasons,
not embedding luck. Live mode swaps in text-embedding-v4 and re-runs the
same bench.

Components:
- embed():  per-token SHAKE-256 pseudo-vectors, summed and L2-normalized.
            Deterministic across platforms/processes.
- rerank(): set-overlap cosine between query and document token sets, in
            [0, 1]. Deterministic keyword-overlap reranker.
- extract(): fixture-backed. Each seed note has a committed extraction
            fixture (fixtures/ward_5day/extraction/shift_NN/bed_NN.json)
            keyed by the note's SHA-256 — extraction can never silently
            drift from the committed prose.

Tokenization uses a tiny deterministic stemmer (documented, tested) so that
trivial inflections ("allergies"/"allergy") match while true vocabulary gaps
("erythema" vs "rash") stay gaps.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from ..schemas import Episode
from ..util import sha256_hex
from .base import Transport

__all__ = ["FakeQwen", "tokenize"]

_WORD_RE = re.compile(r"[a-z0-9]+")


def _stem(tok: str) -> str:
    """Tiny deterministic suffix stemmer — just enough to match plural and
    -ing/-ed inflections. NOT a linguistic claim; tested for determinism."""
    if len(tok) > 5 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 5 and tok.endswith("ing"):
        return tok[:-3]
    if len(tok) > 4 and tok.endswith("ed"):
        return tok[:-2]
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _WORD_RE.findall(text.lower())]


class FakeQwen(Transport):
    name = "fake"

    def __init__(
        self,
        fixtures_root: str | Path | None = None,
        extraction_map: dict[tuple[int, int], list[dict]] | None = None,
        dim: int = 256,
    ):
        """Either *fixtures_root* (committed ward fixtures) or an inline
        *extraction_map* {(bed, shift): [episode dicts]} — the latter powers
        unit tests and the non-clinical reuse example."""
        self.fixtures_root = Path(fixtures_root) if fixtures_root else None
        self.extraction_map = extraction_map
        self.dim = dim
        self._token_vec_cache: dict[str, list[float]] = {}

    # ------------------------------------------------------------------ #
    # embeddings
    # ------------------------------------------------------------------ #

    def _token_vector(self, token: str) -> list[float]:
        vec = self._token_vec_cache.get(token)
        if vec is None:
            raw = hashlib.shake_256(token.encode("utf-8")).digest(self.dim)
            vec = [(b - 127.5) / 127.5 for b in raw]
            self._token_vec_cache[token] = vec
        return vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            acc = [0.0] * self.dim
            for tok in tokenize(text):
                tv = self._token_vector(tok)
                for i in range(self.dim):
                    acc[i] += tv[i]
            norm = math.sqrt(sum(x * x for x in acc))
            if norm > 0:
                acc = [x / norm for x in acc]
            out.append(acc)
        return out

    # ------------------------------------------------------------------ #
    # rerank
    # ------------------------------------------------------------------ #

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        q = set(tokenize(query))
        scores: list[float] = []
        for doc in documents:
            d = set(tokenize(doc))
            if not q or not d:
                scores.append(0.0)
                continue
            inter = len(q & d)
            scores.append(inter / math.sqrt(len(q) * len(d)))
        return scores

    # ------------------------------------------------------------------ #
    # extraction (fixture-backed)
    # ------------------------------------------------------------------ #

    def extract(self, note_text: str, bed: int, shift: int) -> list[Episode]:
        if self.extraction_map is not None:
            raw = self.extraction_map.get((bed, shift))
            if raw is None:
                raise KeyError(f"no inline extraction for bed {bed} shift {shift}")
            return [Episode.model_validate(e) for e in raw]

        if self.fixtures_root is None:
            raise RuntimeError(
                "FakeQwen needs fixtures_root or extraction_map for extraction"
            )
        path = (
            self.fixtures_root
            / "extraction"
            / f"shift_{shift:02d}"
            / f"bed_{bed:02d}.json"
        )
        if not path.exists():
            raise FileNotFoundError(f"missing extraction fixture: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = data["note_sha256"]
        actual = sha256_hex(note_text)
        if actual != expected:
            raise ValueError(
                f"extraction fixture drift for bed {bed} shift {shift}: "
                f"note sha256 {actual} != fixture {expected}"
            )
        return [Episode.model_validate(e) for e in data["episodes"]]
