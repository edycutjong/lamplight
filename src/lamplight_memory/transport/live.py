"""LiveQwen — Qwen Cloud transport (STATUS: code path present, not exercised
offline; see README Status).

Surfaces used (verified model names only):
- qwen3.7-plus       episode extraction + brief SBAR prose (structured output)
- text-embedding-v4  episodic store embeddings (dimensions=256 to match the
                     offline store layout)
- qwen3-rerank       precision stage before the budget packer
- fun-asr            diarized voice handover ingest (live only)

qwen3.7-max is used ONLY for optional seed-prose drafting (seed.py --llm,
disclosed); it is intentionally absent from this runtime transport.

Endpoint: OpenAI-compatible mode at
    https://dashscope-intl.aliyuncs.com/compatible-mode/v1
with DASHSCOPE_API_KEY. Rerank and ASR are not OpenAI-shaped, so they call
the DashScope-native REST endpoints via httpx (documented best-effort —
verify request shapes against the console docs before a live demo; both are
flagged in docs/friction-log.md).
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..schemas import EXTRACTION_JSON_SCHEMA, DecayClass, Episode, EpisodeType
from .base import Transport

__all__ = ["LiveQwen", "BASE_URL"]

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_RERANK_URL = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/"
    "text-rerank/text-rerank"
)

EXTRACT_MODEL = "qwen3.7-plus"
BRIEF_MODEL = "qwen3.7-plus"
EMBED_MODEL = "text-embedding-v4"
RERANK_MODEL = "qwen3-rerank"
ASR_MODEL = "fun-asr"

_EXTRACT_SYSTEM = """You extract structured memory episodes from one nursing shift note.
Rules:
- Split the note into distinct clinical facts. Preserve the note's wording where possible.
- type: observation | action | resolution | order.
- decay_class: critical (allergy-suspect, adverse-reaction-suspect, falls risk,
  safety precautions), condition (active clinical condition being tracked),
  routine (vitals, meals, ambulation, sleep, hygiene), resolved (only for
  resolution statements).
- entities: short lowercase snake_case slugs (e.g. cefazolin, skin_reaction,
  falls_risk, iv_site, sleep). Reuse slugs from the bed context you are given.
- polarity: pos/neg only when the fact asserts a clearly positive or negative
  patient state that could contradict another report; else neutral.
- resolves: for resolution episodes, the entity slug being resolved.
- why_hint: one short clause on why this matters for the coming shift, if obvious.
Return JSON matching the provided schema. Do not invent facts."""


class LiveQwen(Transport):
    name = "live"

    def __init__(self, api_key: str | None = None, dim: int = 256):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "LiveQwen requires DASHSCOPE_API_KEY (offline judging uses "
                "the fake transport: --transport fake)"
            )
        self.dim = dim
        from openai import OpenAI  # lazy import: offline paths never need it

        # Qwen3 models default to "thinking" mode (thousands of reasoning
        # tokens per call, ~45s), which hangs large-prompt live runs. We turn
        # thinking OFF explicitly on each chat call below; here we give the
        # client a generous request timeout and a small retry budget so a slow
        # first token fails fast rather than hanging the whole handover.
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=BASE_URL,
            timeout=120.0,
            max_retries=2,
        )

    # ------------------------------------------------------------------ #

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        # DashScope caps embedding batch sizes; chunk conservatively.
        for i in range(0, len(texts), 10):
            resp = self.client.embeddings.create(
                model=EMBED_MODEL, input=texts[i : i + 10], dimensions=self.dim
            )
            for item in sorted(resp.data, key=lambda d: d.index):
                vec = list(item.embedding)
                norm = sum(x * x for x in vec) ** 0.5
                out.append([x / norm for x in vec] if norm else vec)
        return out

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """qwen3-rerank via the DashScope-native endpoint (not OpenAI-shaped)."""
        import httpx

        resp = httpx.post(
            _RERANK_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": RERANK_MODEL,
                "input": {"query": query, "documents": documents},
                "parameters": {"return_documents": False, "top_n": len(documents)},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        results = resp.json()["output"]["results"]
        scores = [0.0] * len(documents)
        for r in results:
            scores[int(r["index"])] = float(r["relevance_score"])
        return scores

    def extract(self, note_text: str, bed: int, shift: int) -> list[Episode]:
        resp = self.client.chat.completions.create(
            model=EXTRACT_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": f"Bed {bed}, shift {shift}. Shift note:\n\n{note_text}",
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": EXTRACTION_JSON_SCHEMA,
            },
            temperature=0.0,
            # Structured extraction, not open-ended reasoning: keep Qwen3's
            # thinking mode OFF so this returns in seconds, not ~45s.
            extra_body={"enable_thinking": False},
        )
        data = json.loads(resp.choices[0].message.content)
        episodes: list[Episode] = []
        for k, raw in enumerate(data.get("episodes", []), start=1):
            episodes.append(
                Episode(
                    id=f"ep-{bed:02d}-{shift:02d}-{k}",
                    bed=bed,
                    shift=shift,
                    ts="",  # engine assigns ward-clock ts
                    type=EpisodeType(raw["type"]),
                    text=raw["text"],
                    entities=raw.get("entities", []),
                    polarity=raw.get("polarity", "neutral"),
                    decay_class=DecayClass(raw["decay_class"]),
                    resolves=raw.get("resolves"),
                    why_hint=raw.get("why_hint"),
                )
            )
        return episodes

    def brief_prose(self, context: dict) -> dict | None:
        """SBAR prose for one card. Citations are attached mechanically by
        the builder afterwards — the model cannot invent or drop them."""
        resp = self.client.chat.completions.create(
            model=BRIEF_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write one SBAR handover item for a nurse, <= 80 words, "
                        "as JSON {\"sbar\": str, \"why_tonight\": str}. Use ONLY "
                        "the provided facts; do not add clinical claims."
                    ),
                },
                {"role": "user", "content": json.dumps(context)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            # Short constrained SBAR prose from provided facts: no chain-of-
            # thought needed. Thinking OFF to avoid the ~45s reasoning stall.
            extra_body={"enable_thinking": False},
        )
        try:
            return json.loads(resp.choices[0].message.content)
        except json.JSONDecodeError:
            return None  # builder falls back to the deterministic template

    def transcribe(self, audio_path: str) -> str:
        """fun-asr diarized voice-handover ingest. LIVE-ONLY and UNVERIFIED
        offline: the async-task request shape below follows the DashScope ASR
        docs pattern but must be smoke-tested against the console before a
        live demo (friction-logged). Raises rather than degrade silently."""
        import time

        import httpx

        submit = httpx.post(
            "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/asr/transcription",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": ASR_MODEL,
                "input": {"file_urls": [audio_path]},
                "parameters": {"diarization_enabled": True},
            },
            timeout=60.0,
        )
        submit.raise_for_status()
        task_id = submit.json()["output"]["task_id"]
        for _ in range(60):
            poll = httpx.get(
                f"https://dashscope-intl.aliyuncs.com/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
            poll.raise_for_status()
            out: dict[str, Any] = poll.json()["output"]
            status = out.get("task_status")
            if status == "SUCCEEDED":
                return json.dumps(out.get("results", out))
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"fun-asr task {task_id} {status}")
            time.sleep(2.0)
        raise TimeoutError(f"fun-asr task {task_id} did not finish")
