"""LamplightEngine — the full memory lifecycle for one ward database.

ingest_shift(n, notes_dir):
    extract -> seal -> embed -> store -> signed `write` ops
    process resolutions       -> retire targets -> signed `expire` ops
    decay sweep at shift close -> signed `decay` (+ `expire`) ops
    night shifts (n % 3 == 0)  -> contradiction flags (`contradict` ops)
                                  then consolidation (`consolidate` ops)

brief(bed): retrieval -> rerank -> knapsack -> validated SBAR brief.

All timestamps come from the ward clock; every mutation is a signed,
hash-chained ledger entry (COMPLEXITY.md). With the fake transport the whole
lifecycle is deterministic — replaying the fixtures reproduces byte-identical
briefs (I5) and an identical op chain.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from nacl.public import PrivateKey
from nacl.signing import SigningKey

from .brief import DEFAULT_BUDGET, BriefBuilder
from .chain import ChainAudit, ChainReport, OpChain
from .clock import iso, shift_close, shift_start
from .consolidate import Consolidator, entity_slug
from .contradiction import ContradictionResolver
from .decay import DecayPolicy
from .schemas import Brief, Episode, EpisodeType, OpType
from .sealed import Sealer
from .store import MemoryStore
from .transport.base import Transport
from .util import sha256_hex

__all__ = ["LamplightEngine"]

_BED_FILE_RE = re.compile(r"bed_(\d+)\.txt$")


def _episode_offset_minutes(k: int) -> int:
    """Deterministic in-shift timestamp offset for the k-th episode (1-based)."""
    return 90 + 45 * (k - 1)


class LamplightEngine:
    def __init__(
        self,
        db_path: str | Path,
        transport: Transport,
        seal: bool = True,
        signing_key: SigningKey | None = None,
        sealing_key: PrivateKey | None = None,
    ):
        self.db_path = str(db_path)
        self.transport = transport
        self.seal = seal
        self.store = MemoryStore(self.db_path)
        self.chain = OpChain(self.db_path, signing_key=signing_key)
        self.sealer = Sealer(sealing_key) if seal else None
        self.policy = DecayPolicy()
        self.builder = BriefBuilder(
            self.store, transport, self.policy, text_of=self.text_of
        )
        self.consolidator = Consolidator(self.store, text_of=self.text_of)
        self.contradictions = ContradictionResolver(self.store, text_of=self.text_of)

    def close(self) -> None:
        self.store.close()
        self.chain.close()

    # ------------------------------------------------------------------ #
    # plaintext materialization (sealed-at-rest support)
    # ------------------------------------------------------------------ #

    def text_of(self, item_id: str) -> str:
        got = self.store.get_row(item_id)
        if got is None:
            raise KeyError(f"unknown item: {item_id}")
        _, row = got
        if row["text"] is not None:
            return row["text"]
        blob = self.store.get_sealed(item_id)
        if blob is None:
            raise RuntimeError(f"{item_id}: no plaintext and no sealed envelope")
        if self.sealer is None:
            raise RuntimeError(f"{item_id} is sealed but engine has no sealer")
        return self.sealer.unseal(blob)

    def _seal_args(self, text: str) -> tuple[str | None, bytes | None]:
        if self.seal and self.sealer is not None:
            return None, self.sealer.seal(text)
        return text, None

    # ------------------------------------------------------------------ #
    # ingest
    # ------------------------------------------------------------------ #

    def ingest_shift(self, shift: int, notes_dir: str | Path) -> dict:
        """Ingest every bed note for one shift and run the close-of-shift
        lifecycle. Returns a summary dict (episode/op counts)."""
        notes_dir = Path(notes_dir)
        files = sorted(
            p for p in notes_dir.iterdir()
            if p.is_file() and _BED_FILE_RE.search(p.name)
        )
        if not files:
            raise FileNotFoundError(f"no bed_*.txt notes found in {notes_dir}")

        written: list[Episode] = []
        for path in files:
            bed = int(_BED_FILE_RE.search(path.name).group(1))
            note_text = path.read_text(encoding="utf-8")
            episodes = self.transport.extract(note_text, bed=bed, shift=shift)
            texts = [ep.text for ep in episodes]
            vectors = self.transport.embed(texts) if texts else []
            for k, (ep, vec) in enumerate(zip(episodes, vectors), start=1):
                if not ep.ts:  # live transport leaves ts empty
                    ep = ep.model_copy(
                        update={
                            "ts": iso(
                                shift_start(shift)
                                + timedelta(minutes=_episode_offset_minutes(k))
                            )
                        }
                    )
                text_plain, sealed_blob = self._seal_args(ep.text)
                self.store.add_episode(ep, vec, text_plain, sealed_blob)
                self.chain.append(
                    OpType.WRITE,
                    {
                        "id": ep.id,
                        "bed": ep.bed,
                        "shift": ep.shift,
                        "ts": ep.ts,
                        "type": ep.type.value,
                        "entities": ep.entities,
                        "polarity": ep.polarity,
                        "decay_class": ep.decay_class.value,
                        "resolves": ep.resolves,
                        "why_hint": ep.why_hint,
                        "text_sha256": sha256_hex(ep.text),
                        "sealed": bool(sealed_blob),
                    },
                    ts=ep.ts,
                )
                written.append(ep)

        ops = {"write": len(written), "expire": 0, "decay": 0, "contradict": 0, "consolidate": 0}
        ops["expire"] += self._process_resolutions(shift, written)
        expired, decayed = self._decay_sweep(shift)
        ops["expire"] += expired
        ops["decay"] += decayed
        if shift % 3 == 0:  # night close -> nightly consolidation
            c, m = self._nightly(shift)
            ops["contradict"] += c
            ops["consolidate"] += m
        return {"shift": shift, "episodes": len(written), "ops": ops}

    def _process_resolutions(self, shift: int, written: list[Episode]) -> int:
        n_ops = 0
        resolutions = sorted(
            (ep for ep in written if ep.type is EpisodeType.RESOLUTION and ep.resolves),
            key=lambda e: e.id,
        )
        for ep in resolutions:
            entity = entity_slug(ep.resolves)
            targets: list[str] = []
            for row in self.store.active_episode_rows(ep.bed, shift):
                import json as _json

                if row["id"] == ep.id:
                    continue  # pragma: no cover — a resolution episode retires
                    # itself immediately on insert (add_episode), so its own
                    # resolved_shift always equals `shift`; the active-clause
                    # (`resolved_shift > as_of`) therefore excludes it from
                    # this very query before this guard could ever see it.
                    # Kept as a defensive guard against that invariant
                    # changing in the future, not exercised by design.
                if entity in [entity_slug(e) for e in _json.loads(row["entities"])]:
                    targets.append(row["id"])
            for row in self.store.active_memory_rows(ep.bed, shift):
                import json as _json

                if entity in [entity_slug(e) for e in _json.loads(row["entities"])]:
                    targets.append(row["id"])
            targets = sorted(set(targets))
            if not targets:
                continue
            changed = self.store.mark_resolved(targets, shift)
            if changed:
                self.chain.append(
                    OpType.EXPIRE,
                    {
                        "reason": "resolved",
                        "bed": ep.bed,
                        "entity": entity,
                        "resolved_by": ep.id,
                        "ids": sorted(changed),
                        "shift": shift,
                    },
                    ts=ep.ts,
                )
                n_ops += 1
        return n_ops

    def _decay_sweep(self, shift: int) -> tuple[int, int]:
        now = iso(shift_close(shift))
        sweep: list[dict] = []
        to_expire: list[str] = []
        for row in self.store.sweep_targets(shift):
            strength = self.policy.strength(
                row["decay_class"], row["s0"], row["t0"], now, status=row["status"]
            )
            sweep.append({"id": row["id"], "strength": round(strength, 6)})
            if self.policy.is_expired(strength, row["decay_class"]):
                to_expire.append(row["id"])
        expire_ops = 0
        if to_expire:
            changed = self.store.mark_expired(sorted(to_expire), shift)
            if changed:
                self.chain.append(
                    OpType.EXPIRE,
                    {
                        "reason": "decayed_below_threshold",
                        "threshold": self.policy.EXPIRY_THRESHOLD,
                        "ids": sorted(changed),
                        "shift": shift,
                    },
                    ts=now,
                )
                expire_ops = 1
        self.chain.append(
            OpType.DECAY,
            {"shift": shift, "swept": len(sweep), "items": sweep},
            ts=now,
        )
        return expire_ops, 1

    def _nightly(self, shift: int) -> tuple[int, int]:
        now = iso(shift_close(shift))
        beds = [
            int(r["bed"])
            for r in self.store.conn.execute(
                "SELECT DISTINCT bed FROM episodes ORDER BY bed"
            ).fetchall()
        ]
        n_contradict = 0
        n_consolidate = 0
        for bed in beds:
            # contradictions first — the conflicting pair must not be blended
            for flag in self.contradictions.detect(bed, shift):
                vec = self.transport.embed([flag.memory.text])[0]
                text_plain, sealed_blob = self._seal_args(flag.memory.text)
                self.store.add_memory(
                    flag.memory, vec, text_plain, sealed_blob,
                    family=flag.family, supersedes=None,
                )
                self.store.set_merged(list(flag.pair), flag.memory.id, shift)
                self.chain.append(
                    OpType.CONTRADICT,
                    {
                        "memory_id": flag.memory.id,
                        "bed": bed,
                        "entities": flag.memory.entities,
                        "provenance": flag.memory.provenance,
                        "needs_confirmation": True,
                        "text_sha256": sha256_hex(flag.memory.text),
                        "shift": shift,
                    },
                    ts=now,
                )
                n_contradict += 1
            for res in self.consolidator.run(bed, shift):
                vec = self.transport.embed([res.memory.text])[0]
                text_plain, sealed_blob = self._seal_args(res.memory.text)
                self.store.add_memory(
                    res.memory, vec, text_plain, sealed_blob,
                    family=res.family, supersedes=res.supersedes,
                )
                self.store.set_merged(res.newly_merged, res.memory.id, shift)
                self.chain.append(
                    OpType.CONSOLIDATE,
                    {
                        "memory_id": res.memory.id,
                        "family": res.family,
                        "bed": bed,
                        "provenance": res.memory.provenance,
                        "supersedes": res.supersedes,
                        "decay_class": res.memory.decay_class.value,
                        "text_sha256": sha256_hex(res.memory.text),
                        "shift": shift,
                    },
                    ts=now,
                )
                n_consolidate += 1
        return n_contradict, n_consolidate

    # ------------------------------------------------------------------ #
    # brief / feedback / pin
    # ------------------------------------------------------------------ #

    def brief(
        self,
        bed: int,
        as_of_shift: int | None = None,
        budget: int = DEFAULT_BUDGET,
        save: bool = True,
    ) -> Brief:
        if as_of_shift is None:
            as_of_shift = self.store.max_ingested_shift()
        if as_of_shift < 1:
            raise ValueError("nothing ingested yet — run `lamplight ingest` first")
        brief = self.builder.build(bed, as_of_shift, budget=budget)
        if save:
            self.store.save_brief(brief)
        return brief

    def pin(self, item_id: str, ts: str | None = None) -> bool:
        ok = self.store.pin(item_id)
        if ok:
            self.chain.append(
                OpType.PIN,
                {"id": item_id},
                ts=ts or iso(shift_close(max(1, self.store.max_ingested_shift()))),
            )
        return ok

    def feedback(
        self, brief_id: int, card_ix: int, action: str, ts: str | None = None
    ) -> dict:
        """confirm -> strength bump (s0 += 0.25, clock reset); correct ->
        halve s0; dismiss -> expire. Every path is a signed op."""
        saved = self.store.get_brief(brief_id)
        if saved is None:
            raise KeyError(f"unknown brief id {brief_id}")
        cards = saved["payload"]["cards"]
        if not (0 <= card_ix < len(cards)):
            raise IndexError(f"card index {card_ix} out of range")
        card = cards[card_ix]
        item_id = card["source_id"]
        now = ts or iso(shift_close(max(1, self.store.max_ingested_shift())))
        self.store.add_feedback(brief_id, card_ix, action, now)

        got = self.store.get_row(item_id)
        if got is None:
            raise KeyError(f"card source {item_id} not found")
        kind, row = got

        if action == "confirm":
            new_s0 = self.policy.confirm(float(row["s0"]))
            self.store.update_strength(item_id, new_s0, t0=now)
            if kind == "memory" and row.get("needs_confirmation"):
                self.store.confirm_memory(item_id)
            self.chain.append(
                OpType.WRITE,
                {"kind": "confirm", "id": item_id, "s0": round(new_s0, 6)},
                ts=now,
            )
            return {"action": action, "id": item_id, "s0": new_s0}
        if action == "correct":
            new_s0 = max(0.0, float(row["s0"]) * 0.5)
            self.store.update_strength(item_id, new_s0)
            self.chain.append(
                OpType.DECAY,
                {"kind": "correct", "id": item_id, "s0": round(new_s0, 6)},
                ts=now,
            )
            return {"action": action, "id": item_id, "s0": new_s0}
        if action == "dismiss":
            shift = self.store.max_ingested_shift()
            changed = self.store.mark_expired([item_id], shift)
            self.chain.append(
                OpType.EXPIRE,
                {"reason": "dismissed", "ids": changed, "shift": shift},
                ts=now,
            )
            return {"action": action, "id": item_id, "expired": bool(changed)}
        raise ValueError(f"unknown feedback action: {action!r}")

    # ------------------------------------------------------------------ #

    def verify_chain(self) -> ChainReport:
        audit = ChainAudit(self.db_path)
        try:
            return audit.verify()
        finally:
            audit.close()
