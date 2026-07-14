"""MemoryStore — SQLite-backed episodic + semantic memory with vector search.

Design notes
------------
- **No external vector DB.** Embeddings are stored as JSON float lists and
  cosine similarity is computed in pure Python. The ward is small (a few
  hundred vectors); correctness and zero-dependency judging beat pgvector.
- **Time travel.** Every state transition records the *shift* at which it
  happened (`resolved_shift`, `expired_shift`, `merged_at_shift`,
  `superseded_shift`). Queries take `as_of` (a shift number, meaning "state
  after that shift closed"), so one fully-ingested database can serve the
  brief for ANY shift deterministically — this powers the bench and replay.
- **Sealed at rest.** When ECIES sealing is on, the plaintext `text` column
  stays NULL and ciphertext lives in `envelopes`; embeddings and metadata
  remain queryable (COMPLEXITY.md §2). The store never decrypts.
- **Memories are immutable versions.** Consolidation never mutates a memory;
  it writes a new version row and marks the old one superseded. Citations and
  provenance therefore stay historically accurate for any `as_of`.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import Brief, DecayClass, Episode, EpisodeType, MemoryItem, Status
from .util import canonical_json, sha256_hex

__all__ = ["MemoryStore", "Candidate", "cosine"]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Inputs are expected L2-normalized (transports
    guarantee this); falls back to full normalization if not."""
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass(frozen=True)
class Candidate:
    """A retrieval candidate for the brief builder (text may be sealed —
    the engine materializes plaintext before reranking)."""

    id: str
    kind: str  # "episode" | "memory"
    bed: int
    text: str | None
    entities: list[str]
    decay_class: str
    status: str
    s0: float
    t0: str
    needs_confirmation: bool
    provenance: list[str]  # episodes: [own id]; memories: episode IDs
    why_hint: str | None
    first_shift: int  # earliest evidence shift (for SBAR background)
    last_shift: int  # latest evidence shift
    embedding: list[float]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    bed INTEGER NOT NULL,
    shift INTEGER NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    text TEXT,                -- NULL when sealed at rest
    text_sha256 TEXT NOT NULL,
    entities TEXT NOT NULL,   -- JSON list
    polarity TEXT NOT NULL,
    decay_class TEXT NOT NULL,
    status TEXT NOT NULL,
    s0 REAL NOT NULL,
    t0 TEXT NOT NULL,
    resolves TEXT,
    why_hint TEXT,
    created_shift INTEGER NOT NULL,
    resolved_shift INTEGER,
    expired_shift INTEGER,
    merged_into TEXT,
    merged_at_shift INTEGER,
    embedding TEXT NOT NULL   -- JSON list of floats
);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    family TEXT NOT NULL,     -- stable id across versions, e.g. mem-09-cefazolin
    bed INTEGER NOT NULL,
    kind TEXT NOT NULL,       -- consolidated | contradiction
    text TEXT,
    text_sha256 TEXT NOT NULL,
    entities TEXT NOT NULL,
    decay_class TEXT NOT NULL,
    status TEXT NOT NULL,
    s0 REAL NOT NULL,
    t0 TEXT NOT NULL,
    provenance TEXT NOT NULL, -- JSON list of episode ids
    needs_confirmation INTEGER NOT NULL DEFAULT 0,
    why_hint TEXT,
    created_shift INTEGER NOT NULL,
    resolved_shift INTEGER,
    expired_shift INTEGER,
    superseded_shift INTEGER,
    embedding TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS envelopes (
    item_id TEXT PRIMARY KEY,
    sealed_blob BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bed INTEGER NOT NULL,
    as_of_shift INTEGER NOT NULL,
    payload TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL,
    card_ix INTEGER NOT NULL,
    action TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ep_bed ON episodes(bed, created_shift);
CREATE INDEX IF NOT EXISTS idx_mem_bed ON memories(bed, created_shift);
CREATE INDEX IF NOT EXISTS idx_mem_family ON memories(family);
"""


class MemoryStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ #
    # writes
    # ------------------------------------------------------------------ #

    def add_episode(
        self,
        ep: Episode,
        embedding: list[float],
        text_plain: str | None,
        sealed_blob: bytes | None,
    ) -> None:
        """Insert an episode. Resolution-type / resolved-class episodes retire
        immediately (SPEC §5: resolved -> 'retired immediately')."""
        if self.exists(ep.id):
            raise ValueError(f"duplicate episode id: {ep.id}")
        retired = ep.type is EpisodeType.RESOLUTION or ep.decay_class is DecayClass.RESOLVED
        status = Status.RESOLVED if retired else Status.ACTIVE
        resolved_shift = ep.shift if retired else None
        self.conn.execute(
            """INSERT INTO episodes
               (id, bed, shift, ts, type, text, text_sha256, entities, polarity,
                decay_class, status, s0, t0, resolves, why_hint, created_shift,
                resolved_shift, expired_shift, merged_into, merged_at_shift, embedding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?)""",
            (
                ep.id, ep.bed, ep.shift, ep.ts, ep.type.value, text_plain,
                sha256_hex(ep.text), canonical_json(ep.entities), ep.polarity,
                ep.decay_class.value, status.value, 1.0, ep.ts, ep.resolves,
                ep.why_hint, ep.shift, resolved_shift,
                canonical_json(embedding),
            ),
        )
        if sealed_blob is not None:
            self.conn.execute(
                "INSERT OR REPLACE INTO envelopes (item_id, sealed_blob) VALUES (?,?)",
                (ep.id, sealed_blob),
            )
        self.conn.commit()

    def add_memory(
        self,
        mem: MemoryItem,
        embedding: list[float],
        text_plain: str | None,
        sealed_blob: bytes | None,
        family: str,
        supersedes: str | None = None,
    ) -> None:
        if self.exists(mem.id):
            raise ValueError(f"duplicate memory id: {mem.id}")
        t0 = None
        # t0 = consolidation moment (close of created_shift) — set by caller
        # via mem? Use created shift close.
        from .clock import iso, shift_close  # local import to avoid cycle

        t0 = iso(shift_close(mem.created_shift))
        self.conn.execute(
            """INSERT INTO memories
               (id, family, bed, kind, text, text_sha256, entities, decay_class,
                status, s0, t0, provenance, needs_confirmation, why_hint,
                created_shift, resolved_shift, expired_shift, superseded_shift, embedding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?)""",
            (
                mem.id, family, mem.bed, mem.kind, text_plain, sha256_hex(mem.text),
                canonical_json(mem.entities), mem.decay_class.value,
                Status.ACTIVE.value, 1.0, t0, canonical_json(mem.provenance),
                int(mem.needs_confirmation), mem.why_hint, mem.created_shift,
                canonical_json(embedding),
            ),
        )
        if sealed_blob is not None:
            self.conn.execute(
                "INSERT OR REPLACE INTO envelopes (item_id, sealed_blob) VALUES (?,?)",
                (mem.id, sealed_blob),
            )
        if supersedes is not None:
            self.conn.execute(
                "UPDATE memories SET superseded_shift = ? WHERE id = ?",
                (mem.created_shift, supersedes),
            )
        self.conn.commit()

    def mark_resolved(self, ids: Iterable[str], shift: int) -> list[str]:
        """Retire items by explicit resolution. Returns ids actually changed."""
        changed: list[str] = []
        for item_id in ids:
            for table in ("episodes", "memories"):
                cur = self.conn.execute(
                    f"UPDATE {table} SET status=?, resolved_shift=? "
                    f"WHERE id=? AND status=?",
                    (Status.RESOLVED.value, shift, item_id, Status.ACTIVE.value),
                )
                if cur.rowcount:
                    changed.append(item_id)
        self.conn.commit()
        return changed

    def mark_expired(self, ids: Iterable[str], shift: int) -> list[str]:
        changed: list[str] = []
        for item_id in ids:
            for table in ("episodes", "memories"):
                cur = self.conn.execute(
                    f"UPDATE {table} SET status=?, expired_shift=? "
                    f"WHERE id=? AND status=?",
                    (Status.EXPIRED.value, shift, item_id, Status.ACTIVE.value),
                )
                if cur.rowcount:
                    changed.append(item_id)
        self.conn.commit()
        return changed

    def set_merged(self, ep_ids: Iterable[str], mem_id: str, shift: int) -> None:
        for ep_id in ep_ids:
            self.conn.execute(
                "UPDATE episodes SET merged_into=?, merged_at_shift=? "
                "WHERE id=? AND merged_into IS NULL",
                (mem_id, shift, ep_id),
            )
        self.conn.commit()

    def pin(self, item_id: str) -> bool:
        ok = False
        for table in ("episodes", "memories"):
            cur = self.conn.execute(
                f"UPDATE {table} SET status=? WHERE id=? AND status=?",
                (Status.PINNED.value, item_id, Status.ACTIVE.value),
            )
            ok = ok or bool(cur.rowcount)
        self.conn.commit()
        return ok

    def update_strength(self, item_id: str, s0: float, t0: str | None = None) -> bool:
        ok = False
        for table in ("episodes", "memories"):
            if t0 is None:
                cur = self.conn.execute(
                    f"UPDATE {table} SET s0=? WHERE id=?", (s0, item_id)
                )
            else:
                cur = self.conn.execute(
                    f"UPDATE {table} SET s0=?, t0=? WHERE id=?", (s0, t0, item_id)
                )
            ok = ok or bool(cur.rowcount)
        self.conn.commit()
        return ok

    def confirm_memory(self, mem_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE memories SET needs_confirmation=0 WHERE id=?", (mem_id,)
        )
        self.conn.commit()
        return bool(cur.rowcount)

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    def exists(self, item_id: str) -> bool:
        for table in ("episodes", "memories"):
            if self.conn.execute(
                f"SELECT 1 FROM {table} WHERE id=?", (item_id,)
            ).fetchone():
                return True
        return False

    def get_row(self, item_id: str) -> tuple[str, dict[str, Any]] | None:
        """Return ("episode"|"memory", row-dict) or None."""
        row = self.conn.execute(
            "SELECT * FROM episodes WHERE id=?", (item_id,)
        ).fetchone()
        if row:
            return "episode", dict(row)
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id=?", (item_id,)
        ).fetchone()
        if row:
            return "memory", dict(row)
        return None

    def get_sealed(self, item_id: str) -> bytes | None:
        row = self.conn.execute(
            "SELECT sealed_blob FROM envelopes WHERE item_id=?", (item_id,)
        ).fetchone()
        return bytes(row["sealed_blob"]) if row else None

    @staticmethod
    def _active_clause(as_of: int, alias: str = "") -> str:
        p = f"{alias}." if alias else ""
        return (
            f"{p}created_shift <= {as_of} "
            f"AND ({p}resolved_shift IS NULL OR {p}resolved_shift > {as_of}) "
            f"AND ({p}expired_shift IS NULL OR {p}expired_shift > {as_of})"
        )

    def status_at(self, item_id: str, as_of: int) -> Status | None:
        """Status of an item as of a shift close. None if it does not exist
        (or was not yet created) at that point."""
        got = self.get_row(item_id)
        if got is None:
            return None
        _, row = got
        if row["created_shift"] > as_of:
            return None
        if row["resolved_shift"] is not None and row["resolved_shift"] <= as_of:
            return Status.RESOLVED
        if row["expired_shift"] is not None and row["expired_shift"] <= as_of:
            return Status.EXPIRED
        if row["status"] == Status.PINNED.value:
            return Status.PINNED
        return Status.ACTIVE

    def active_episode_rows(
        self, bed: int | None, as_of: int, for_brief: bool = False
    ) -> list[dict[str, Any]]:
        q = f"SELECT * FROM episodes WHERE {self._active_clause(as_of)}"
        args: list[Any] = []
        if bed is not None:
            q += " AND bed=?"
            args.append(bed)
        if for_brief:
            q += (
                " AND type != 'resolution' AND decay_class != 'resolved'"
                f" AND (merged_into IS NULL OR merged_at_shift > {as_of})"
            )
        q += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def active_memory_rows(self, bed: int | None, as_of: int) -> list[dict[str, Any]]:
        q = (
            f"SELECT * FROM memories WHERE {self._active_clause(as_of)} "
            f"AND (superseded_shift IS NULL OR superseded_shift > {as_of})"
        )
        args: list[Any] = []
        if bed is not None:
            q += " AND bed=?"
            args.append(bed)
        q += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def latest_memory_version(self, family: str, as_of: int) -> dict[str, Any] | None:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE family=? AND created_shift<=? "
            "ORDER BY created_shift DESC, id DESC LIMIT 1",
            (family, as_of),
        ).fetchone()
        return dict(rows) if rows else None

    def all_episode_rows(self, bed: int | None, max_shift: int) -> list[dict[str, Any]]:
        """Naive-RAG view: every raw episode regardless of status/merge —
        exactly what a baseline vector store would contain."""
        q = "SELECT * FROM episodes WHERE shift <= ?"
        args: list[Any] = [max_shift]
        if bed is not None:
            q += " AND bed=?"
            args.append(bed)
        q += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def retired_rows(self, bed: int, as_of: int) -> list[dict[str, Any]]:
        """Non-routine items retired (resolved/expired) by `as_of` — the
        strikethrough panel. Routine expiry is summarized as a count."""
        rows = self.conn.execute(
            """SELECT * FROM episodes WHERE bed=? AND decay_class IN ('critical','condition')
               AND ((resolved_shift IS NOT NULL AND resolved_shift <= ?)
                 OR (expired_shift IS NOT NULL AND expired_shift <= ?))
               AND type != 'resolution'
               ORDER BY id""",
            (bed, as_of, as_of),
        ).fetchall()
        mems = self.conn.execute(
            """SELECT * FROM memories WHERE bed=?
               AND ((resolved_shift IS NOT NULL AND resolved_shift <= ?)
                 OR (expired_shift IS NOT NULL AND expired_shift <= ?))
               ORDER BY id""",
            (bed, as_of, as_of),
        ).fetchall()
        return [dict(r) for r in rows] + [dict(r) for r in mems]

    def routine_expired_count(self, bed: int, as_of: int) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM episodes WHERE bed=? AND decay_class='routine'
               AND expired_shift IS NOT NULL AND expired_shift <= ?""",
            (bed, as_of),
        ).fetchone()
        return int(row["n"])

    def resolution_for_entity(self, bed: int, entity: str, as_of: int) -> dict | None:
        row = self.conn.execute(
            """SELECT * FROM episodes WHERE bed=? AND type='resolution' AND resolves=?
               AND shift <= ? ORDER BY shift DESC, id LIMIT 1""",
            (bed, entity, as_of),
        ).fetchone()
        return dict(row) if row else None

    def sweep_targets(self, as_of: int) -> list[dict[str, Any]]:
        """All ward items eligible for the decay sweep at a shift close."""
        eps = self.active_episode_rows(None, as_of)
        mems = self.active_memory_rows(None, as_of)
        for m in mems:
            m["_table"] = "memories"
        for e in eps:
            e["_table"] = "episodes"
        return sorted(eps + mems, key=lambda r: r["id"])

    # ------------------------------------------------------------------ #
    # candidates + vector search
    # ------------------------------------------------------------------ #

    def _row_to_candidate(self, row: dict[str, Any], kind: str) -> Candidate:
        if kind == "episode":
            prov = [row["id"]]
            first = last = int(row["shift"])
        else:
            prov = json.loads(row["provenance"])
            shifts = self.episode_shifts(prov)
            first = min(shifts.values()) if shifts else int(row["created_shift"])
            last = max(shifts.values()) if shifts else int(row["created_shift"])
        return Candidate(
            id=row["id"],
            kind=kind,
            bed=int(row["bed"]),
            text=row["text"],
            entities=json.loads(row["entities"]),
            decay_class=row["decay_class"],
            status=row["status"],
            s0=float(row["s0"]),
            t0=row["t0"],
            needs_confirmation=bool(row.get("needs_confirmation", 0)),
            provenance=prov,
            why_hint=row.get("why_hint"),
            first_shift=first,
            last_shift=last,
            embedding=json.loads(row["embedding"]),
        )

    def brief_candidates(self, bed: int, as_of: int) -> list[Candidate]:
        """Active memories + active unmerged non-resolution episodes."""
        out = [
            self._row_to_candidate(r, "memory")
            for r in self.active_memory_rows(bed, as_of)
        ]
        out += [
            self._row_to_candidate(r, "episode")
            for r in self.active_episode_rows(bed, as_of, for_brief=True)
        ]
        return sorted(out, key=lambda c: c.id)

    def top_k(
        self, query_vec: list[float], candidates: list[Candidate], k: int
    ) -> list[tuple[Candidate, float]]:
        scored = [(c, cosine(query_vec, c.embedding)) for c in candidates]
        scored.sort(key=lambda t: (-t[1], t[0].id))
        return scored[:k]

    def episode_shifts(self, ids: list[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for eid in ids:
            row = self.conn.execute(
                "SELECT shift FROM episodes WHERE id=?", (eid,)
            ).fetchone()
            if row:
                out[eid] = int(row["shift"])
        return out

    # ------------------------------------------------------------------ #
    # briefs + feedback
    # ------------------------------------------------------------------ #

    def save_brief(self, brief: Brief) -> int:
        cur = self.conn.execute(
            "INSERT INTO briefs (bed, as_of_shift, payload, token_count, generated_at) "
            "VALUES (?,?,?,?,?)",
            (
                brief.bed,
                brief.as_of_shift,
                canonical_json(brief.model_dump()),
                brief.token_count,
                brief.generated_at,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_brief(self, brief_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM briefs WHERE id=?", (brief_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d

    def add_feedback(self, brief_id: int, card_ix: int, action: str, ts: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO feedback (brief_id, card_ix, action, ts) VALUES (?,?,?,?)",
            (brief_id, card_ix, action, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    def counts(self) -> dict[str, int]:
        out = {}
        for table in ("episodes", "memories", "briefs", "envelopes"):
            out[table] = int(
                self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            )
        return out

    def max_ingested_shift(self) -> int:
        row = self.conn.execute("SELECT MAX(shift) AS m FROM episodes").fetchone()
        return int(row["m"] or 0)
