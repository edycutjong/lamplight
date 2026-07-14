"""Typed schemas: Episode, MemoryItem, BriefCard, Brief, and op/status enums.

These mirror SPEC.md §5 (memory design) and §6 (BriefCard). The same models
validate FakeQwen fixture extractions offline and qwen3.7-plus structured
output live — one schema, two transports.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "DecayClass",
    "Status",
    "EpisodeType",
    "OpType",
    "Episode",
    "MemoryItem",
    "BriefCard",
    "RetiredItem",
    "LeftOutItem",
    "Brief",
    "EXTRACTION_JSON_SCHEMA",
]


class DecayClass(StrEnum):
    """SPEC §5 decay classes.

    critical  — allergy-suspect, falls-risk … no decay until resolved+confirmed
    condition — active clinical condition, half-life 3 days (72 h)
    routine   — vitals/meals/ambulation, half-life 1 shift (8 h)
    resolved  — retired immediately; retrievable in history only
    """

    CRITICAL = "critical"
    CONDITION = "condition"
    ROUTINE = "routine"
    RESOLVED = "resolved"


class Status(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    PINNED = "pinned"


class EpisodeType(StrEnum):
    OBSERVATION = "observation"
    ACTION = "action"
    RESOLUTION = "resolution"
    ORDER = "order"


class OpType(StrEnum):
    """The six signed memory operations (COMPLEXITY.md §2)."""

    WRITE = "write"
    CONSOLIDATE = "consolidate"
    DECAY = "decay"
    CONTRADICT = "contradict"
    PIN = "pin"
    EXPIRE = "expire"


class Episode(BaseModel):
    """One extracted unit of clinical memory (SPEC §5 Episode)."""

    id: str
    bed: int
    shift: int = Field(ge=1)
    ts: str  # ISO-8601, ward clock
    type: EpisodeType
    text: str
    entities: list[str] = Field(default_factory=list)
    polarity: Literal["pos", "neg", "neutral"] = "neutral"
    decay_class: DecayClass
    resolves: str | None = None  # entity retired by a resolution episode
    why_hint: str | None = None  # optional "why tonight" hint from extraction

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("episode text must be non-empty")
        return v

    @field_validator("entities")
    @classmethod
    def _entities_sorted_unique(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class MemoryItem(BaseModel):
    """A semantic memory produced by consolidation (or a contradiction flag)."""

    id: str
    bed: int
    kind: Literal["consolidated", "contradiction"]
    text: str
    entities: list[str] = Field(default_factory=list)
    decay_class: DecayClass
    provenance: list[str] = Field(default_factory=list)  # episode IDs
    needs_confirmation: bool = False
    created_shift: int = Field(ge=1)
    why_hint: str | None = None

    @field_validator("provenance")
    @classmethod
    def _prov_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("memory provenance must cite at least one episode")
        return v


class BriefCard(BaseModel):
    """One SBAR item in a brief (SPEC §6). Citations are mandatory —
    the validator mechanically rejects citation-less cards."""

    bed: int
    priority: int = Field(ge=1)
    sbar: str
    why_tonight: str
    citations: list[str]
    decay_note: str | None = None
    needs_confirmation: bool = False
    source_id: str  # episode or memory the card was built from


class RetiredItem(BaseModel):
    """The strikethrough panel: what memory retired, and why (SPEC §8)."""

    id: str
    label: str
    reason: Literal["resolved", "expired"]
    at_shift: int
    citation: str  # the episode that resolves/retires it


class LeftOutItem(BaseModel):
    """Budget honesty: what the packer did NOT include, and why."""

    id: str
    label: str
    reason: str
    value: float
    tokens: int


class Brief(BaseModel):
    """A complete handover brief for one bed (hard token budget, I3)."""

    bed: int
    as_of_shift: int  # memory state after this shift closed
    for_shift: int  # the incoming shift this brief serves (= as_of_shift + 1)
    generated_at: str  # ward clock, not wall clock (I5)
    engine: Literal["fake", "live"]
    budget: int
    token_count: int
    cards: list[BriefCard]
    retired: list[RetiredItem] = Field(default_factory=list)
    left_out: list[LeftOutItem] = Field(default_factory=list)
    routine_expired_count: int = 0


# JSON schema handed to qwen3.7-plus structured output in live mode.
# FakeQwen fixtures are validated against the same Episode model.
EXTRACTION_JSON_SCHEMA: dict = {
    "name": "episode_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "episodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["observation", "action", "resolution", "order"],
                        },
                        "text": {"type": "string"},
                        "entities": {"type": "array", "items": {"type": "string"}},
                        "polarity": {"type": "string", "enum": ["pos", "neg", "neutral"]},
                        "decay_class": {
                            "type": "string",
                            "enum": ["critical", "condition", "routine", "resolved"],
                        },
                        "resolves": {"type": ["string", "null"]},
                        "why_hint": {"type": ["string", "null"]},
                    },
                    "required": ["type", "text", "entities", "polarity", "decay_class"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["episodes"],
        "additionalProperties": False,
    },
    "strict": True,
}
