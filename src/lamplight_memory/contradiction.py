"""ContradictionResolver — conflicting episodes become human-confirm flags.

Two active episodes on the same bed and entity with opposite polarity within
a 3-shift window (e.g. day nurse: "slept well" vs night nurse: "up 4x
overnight") produce a *contradiction memory*: needs_confirmation=True, cited
provenance = the conflicting pair, and a signed `contradict` op. Until a
human confirms, the flag is priced as CRITICAL in the packer — a conflict
about a patient's state must never silently decay out of the brief.

Rule-based and deterministic offline; live extraction supplies the polarity
labels (qwen3.7-plus structured output), the resolver itself never calls a
model. Runs BEFORE consolidation so the conflicting pair is claimed by the
flag, not blended into a merged memory that would hide the conflict.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from .consolidate import entity_slug
from .schemas import DecayClass, MemoryItem
from .store import MemoryStore

__all__ = ["ContradictionResolver", "ContradictionFlag"]

WINDOW_SHIFTS = 3


@dataclass
class ContradictionFlag:
    memory: MemoryItem
    family: str
    pair: tuple[str, str]  # (pos episode id, neg episode id)


class ContradictionResolver:
    def __init__(self, store: MemoryStore, text_of: Callable[[str], str]):
        self.store = store
        self.text_of = text_of

    def detect(self, bed: int, shift: int) -> list[ContradictionFlag]:
        eps = self.store.active_episode_rows(bed, shift, for_brief=True)
        by_entity: dict[str, dict[str, list[dict]]] = {}
        for ep in eps:
            if ep["polarity"] not in ("pos", "neg"):
                continue
            for ent in json.loads(ep["entities"]):
                slot = by_entity.setdefault(entity_slug(ent), {"pos": [], "neg": []})
                slot[ep["polarity"]].append(ep)

        flags: list[ContradictionFlag] = []
        for entity in sorted(by_entity):
            family = f"mem-c-{bed:02d}-{entity}"
            if self.store.latest_memory_version(family, shift) is not None:
                continue  # one open flag per entity
            pos = sorted(by_entity[entity]["pos"], key=lambda e: (e["shift"], e["id"]))
            neg = sorted(by_entity[entity]["neg"], key=lambda e: (e["shift"], e["id"]))
            pair: tuple[dict, dict] | None = None
            best_key: tuple | None = None
            for a in pos:
                for b in neg:
                    if abs(int(a["shift"]) - int(b["shift"])) > WINDOW_SHIFTS:
                        continue
                    # prefer the most recent conflict, deterministic tie-break
                    key = (
                        -max(int(a["shift"]), int(b["shift"])),
                        a["id"],
                        b["id"],
                    )
                    if best_key is None or key < best_key:
                        best_key, pair = key, (a, b)
            if pair is None:
                continue
            a, b = pair
            first, second = sorted((a, b), key=lambda e: (e["shift"], e["id"]))
            title = entity.replace("_", " ")
            text = (
                f"CONFLICTING REPORTS — {title}: "
                f"\"{self.text_of(first['id'])}\" (shift {first['shift']}) vs "
                f"\"{self.text_of(second['id'])}\" (shift {second['shift']}). "
                f"Needs human confirmation."
            )
            mem = MemoryItem(
                id=f"{family}-s{shift:02d}",
                bed=bed,
                kind="contradiction",
                text=text,
                entities=[entity],
                decay_class=DecayClass.CONDITION,
                provenance=[first["id"], second["id"]],
                needs_confirmation=True,
                created_shift=shift,
                why_hint=f"conflicting {title} reports — confirm with patient/team before charting",
            )
            flags.append(
                ContradictionFlag(memory=mem, family=family, pair=(a["id"], b["id"]))
            )
        return flags
