"""Consolidator — nightly semantic merge (SPEC §5).

At every night-shift close, active episodes that share an entity are merged
into one semantic memory with a full provenance list (the episode IDs the
brief will cite). Memories are *versioned*: extending a thread writes a new
version and supersedes the old one, so historical briefs stay reproducible.

Rules (formalized in docs/SPEC-MEMORY.md):
- An episode can seed at most one memory (first claiming entity in sorted
  order wins) but may appear in another memory's provenance later — the
  claim only controls which item represents it in retrieval.
- A new memory needs >= 2 unclaimed episodes; an existing memory family is
  extended by >= 1 new episode.
- Merged decay class = highest criticality among members
  (critical > condition > routine).
- why_hint = the most recent member's non-null hint (freshest guidance wins).

In live mode the merged prose could be rewritten by qwen3.7-plus on the
Batch API (nightly, -50%); offline the deterministic template below is the
canonical output — the structure (provenance, class, entity) is identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .schemas import DecayClass, MemoryItem
from .store import MemoryStore

__all__ = ["Consolidator", "ConsolidationResult", "entity_slug"]

_CLASS_RANK = {
    DecayClass.CRITICAL.value: 3,
    DecayClass.CONDITION.value: 2,
    DecayClass.ROUTINE.value: 1,
    DecayClass.RESOLVED.value: 0,
}

_SNIPPET_LEN = 160


def entity_slug(entity: str) -> str:
    return entity.strip().lower().replace(" ", "_")


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _SNIPPET_LEN:
        return text
    return text[: _SNIPPET_LEN - 1].rstrip() + "…"


@dataclass
class ConsolidationResult:
    memory: MemoryItem
    family: str
    supersedes: str | None
    newly_merged: list[str]  # episode ids claimed by this version


class Consolidator:
    def __init__(self, store: MemoryStore, text_of: Callable[[str], str]):
        """*text_of(episode_id)* returns plaintext (unsealing if needed) —
        consolidation happens inside the worker, like brief building."""
        self.store = store
        self.text_of = text_of

    def run(self, bed: int, shift: int) -> list[ConsolidationResult]:
        """Consolidate one bed at the close of *shift*. Returns new memory
        versions in deterministic (entity-sorted) order. The caller (engine)
        persists them and signs the consolidate ops."""
        eps = self.store.active_episode_rows(bed, shift, for_brief=True)
        by_entity: dict[str, list[dict]] = {}
        for ep in eps:
            import json as _json

            for ent in _json.loads(ep["entities"]):
                by_entity.setdefault(entity_slug(ent), []).append(ep)

        results: list[ConsolidationResult] = []
        claimed: set[str] = set()

        for entity in sorted(by_entity):
            group = sorted(
                (e for e in by_entity[entity] if e["id"] not in claimed),
                key=lambda e: (e["shift"], e["id"]),
            )
            family = f"mem-{bed:02d}-{entity}"
            existing = self.store.latest_memory_version(family, shift)
            if existing is None and len(group) < 2:
                continue
            if existing is not None and len(group) < 1:
                continue

            import json as _json

            old_prov: list[str] = (
                _json.loads(existing["provenance"]) if existing else []
            )
            new_ids = [e["id"] for e in group]
            provenance = old_prov + [i for i in new_ids if i not in old_prov]
            prov_shifts = self.store.episode_shifts(provenance)
            provenance = sorted(provenance, key=lambda i: (prov_shifts.get(i, 0), i))

            # merged prose: chronological snippets with shift markers
            parts = [
                f"[s{prov_shifts.get(pid, 0):02d}] {_snippet(self.text_of(pid))}"
                for pid in provenance
            ]
            title = entity.replace("_", " ")
            text = f"{title} — thread across {len(provenance)} notes: " + " ".join(parts)

            # class + hint from members (existing memory members included via provenance)
            member_rows = [
                self.store.get_row(pid)[1] for pid in provenance
                if self.store.get_row(pid) is not None
            ]
            decay_class = max(
                (r["decay_class"] for r in member_rows),
                key=lambda c: _CLASS_RANK.get(c, 0),
                default=DecayClass.ROUTINE.value,
            )
            why_hint = None
            for r in sorted(member_rows, key=lambda r: (r["shift"], r["id"])):
                if r.get("why_hint"):
                    why_hint = r["why_hint"]  # latest non-null wins

            entities: set[str] = set()
            for r in member_rows:
                entities.update(entity_slug(e) for e in _json.loads(r["entities"]))

            mem = MemoryItem(
                id=f"{family}-s{shift:02d}",
                bed=bed,
                kind="consolidated",
                text=text,
                entities=sorted(entities),
                decay_class=DecayClass(decay_class),
                provenance=provenance,
                needs_confirmation=False,
                created_shift=shift,
                why_hint=why_hint,
            )
            results.append(
                ConsolidationResult(
                    memory=mem,
                    family=family,
                    supersedes=existing["id"] if existing else None,
                    newly_merged=new_ids,
                )
            )
            claimed.update(new_ids)
        return results
