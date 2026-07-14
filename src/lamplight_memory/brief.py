"""BriefBuilder — retrieval -> rerank -> budget knapsack -> validated SBAR
brief with per-item episode citations (SPEC §5 "Retrieval under budget").

Pipeline (identical fake/live; only the transport differs):
    1. embed the fixed handover query, take top-40 candidates by cosine
       (active memories + active unmerged episodes only — lifecycle first)
    2. rerank (qwen3-rerank live / keyword-overlap fake)
    3. value = rerank_score x decay_strength x criticality
    4. drop duplicate threads (a candidate whose citations are a subset of a
       stronger candidate's)
    5. greedy-pack into the token budget, max 5 cards, log what was left out
    6. mechanical citation validation (I1/I2) — uncited or expired-source
       cards are rejected, never patched

The brief also carries the *retired* panel — what the memory deliberately
forgot (the strikethrough beat) — and `left_out` (budget honesty as UX).
"""

from __future__ import annotations

from collections.abc import Callable

from .clock import iso, shift_close
from .decay import DecayPolicy
from .packer import BudgetPacker, PackCandidate
from .schemas import Brief, BriefCard, DecayClass, LeftOutItem, RetiredItem
from .store import Candidate, MemoryStore
from .tokens import approx_tokens
from .transport.base import Transport
from .validator import CitationValidator

__all__ = ["BriefBuilder", "handover_query", "DEFAULT_BUDGET", "MAX_CARDS"]

DEFAULT_BUDGET = 2000
MAX_CARDS = 5
TOP_K_RETRIEVE = 40

# Rerank calibration (friction-logged): raw rerank scores are query-surface
# measures, and a bare `rerank x strength x criticality` product would zero
# out exactly the items this engine exists to protect — critical facts
# phrased in vocabulary the query never uses ("unsteady ... to the bathroom"
# vs "falls risk"). We therefore calibrate rerank onto a floor:
#     rerank' = RERANK_FLOOR + (1 - RERANK_FLOOR) * rerank
# so lifecycle (decay strength x criticality) decides and rerank refines.
RERANK_FLOOR = 0.3


def handover_query(bed: int) -> str:
    """The fixed retrieval query — identical for Lamplight and the naive
    baseline in the bench, so the comparison is embedding-fair."""
    return (
        f"Handover brief for bed {bed} tonight: allergies and reactions, "
        "high-risk medications, bleeding risk, seizure or safety precautions, "
        "falls risk, IV lines and access, pain, sleep, breathing, mobility, "
        "active concerns."
    )


_ASSESS = {
    DecayClass.CRITICAL.value: "Treat as unresolved critical item.",
    DecayClass.CONDITION.value: "Active condition being tracked.",
    DecayClass.ROUTINE.value: "Routine context.",
}
_RECOMMEND = {
    DecayClass.CRITICAL.value: "Verify before related meds or care tonight; escalate any change.",
    DecayClass.CONDITION.value: "Monitor and reassess this shift.",
    DecayClass.ROUTINE.value: "No action unless status changes.",
}
_WHY_DEFAULT = {
    DecayClass.CRITICAL.value: "Unresolved critical item — must carry into tonight.",
    DecayClass.CONDITION.value: "Active condition — the trend matters tonight.",
    DecayClass.ROUTINE.value: "Context only.",
}


class BriefBuilder:
    def __init__(
        self,
        store: MemoryStore,
        transport: Transport,
        policy: DecayPolicy | None = None,
        text_of: Callable[[str], str] | None = None,
    ):
        self.store = store
        self.transport = transport
        self.policy = policy or DecayPolicy()
        # text_of(item_id) -> plaintext (unseals if needed). Defaults to the
        # plaintext column for unsealed stores.
        self.text_of = text_of or self._plain_text

    def _plain_text(self, item_id: str) -> str:
        got = self.store.get_row(item_id)
        if got is None:
            raise KeyError(item_id)
        _, row = got
        if row["text"] is None:
            raise RuntimeError(
                f"{item_id} is sealed at rest; builder needs a text_of un-sealer"
            )
        return row["text"]

    # ------------------------------------------------------------------ #

    def _render_card(
        self, cand: Candidate, bed: int, retired_by_entity: dict[str, RetiredItem]
    ) -> dict:
        text = " ".join(self.text_of(cand.id).split())
        n = len(cand.provenance)
        span = (
            f"shift s{cand.first_shift:02d}"
            if cand.first_shift == cand.last_shift
            else f"shifts s{cand.first_shift:02d}–s{cand.last_shift:02d}"
        )
        klass = cand.decay_class
        if cand.needs_confirmation:
            assess = "Reports conflict — do not chart either version as fact."
            recommend = "Confirm with patient and outgoing nurse; document the confirmed version."
        else:
            assess = _ASSESS.get(klass, "Review.")
            recommend = _RECOMMEND.get(klass, "Review this shift.")
        sbar = (
            f"S: {text} "
            f"B: Bed {bed} — {n} linked note{'s' if n != 1 else ''}, {span}; "
            f"{klass} class{', UNCONFIRMED conflict' if cand.needs_confirmation else ''}. "
            f"A: {assess} "
            f"R: {recommend}"
        )
        why = cand.why_hint or _WHY_DEFAULT.get(klass, "Review tonight.")

        decay_note = None
        for ent in sorted(cand.entities):
            hit = retired_by_entity.get(ent)
            if hit is not None:
                decay_note = (
                    f"Related item retired: {hit.label} "
                    f"({hit.reason} — see {hit.citation})"
                )
                break

        tokens = (
            approx_tokens(sbar)
            + approx_tokens(why)
            + approx_tokens(decay_note or "")
            + sum(approx_tokens(f"[{c}]") for c in cand.provenance)
        )
        return {
            "sbar": sbar,
            "why_tonight": why,
            "decay_note": decay_note,
            "citations": list(cand.provenance),
            "tokens": tokens,
            "needs_confirmation": cand.needs_confirmation,
            "source_id": cand.id,
        }

    def _retired_panel(self, bed: int, as_of: int) -> list[RetiredItem]:
        items: list[RetiredItem] = []
        for row in self.store.retired_rows(bed, as_of):
            reason = (
                "resolved"
                if row["resolved_shift"] is not None and row["resolved_shift"] <= as_of
                else "expired"
            )
            at_shift = int(
                row["resolved_shift"] if reason == "resolved" else row["expired_shift"]
            )
            citation = row["id"]
            if reason == "resolved":
                import json as _json

                for ent in sorted(_json.loads(row["entities"])):
                    res = self.store.resolution_for_entity(bed, ent, as_of)
                    if res is not None:
                        citation = res["id"]
                        break
            label = " ".join(self.text_of(row["id"]).split())
            if len(label) > 110:
                label = label[:109].rstrip() + "…"
            items.append(
                RetiredItem(
                    id=row["id"], label=label, reason=reason,
                    at_shift=at_shift, citation=citation,
                )
            )
        return sorted(items, key=lambda r: (r.at_shift, r.id))

    # ------------------------------------------------------------------ #

    def build(
        self,
        bed: int,
        as_of_shift: int,
        budget: int = DEFAULT_BUDGET,
        max_cards: int = MAX_CARDS,
    ) -> Brief:
        now = iso(shift_close(as_of_shift))
        query = handover_query(bed)

        retired = self._retired_panel(bed, as_of_shift)
        retired_by_entity: dict[str, RetiredItem] = {}
        for r in retired:
            got = self.store.get_row(r.id)
            if got:
                import json as _json

                for ent in _json.loads(got[1]["entities"]):
                    retired_by_entity.setdefault(ent, r)

        candidates = self.store.brief_candidates(bed, as_of_shift)
        left_out: list[LeftOutItem] = []
        cards: list[BriefCard] = []
        token_count = 0

        if candidates:
            qvec = self.transport.embed([query])[0]
            top = self.store.top_k(qvec, candidates, TOP_K_RETRIEVE)
            docs = [self.text_of(c.id) for c, _ in top]
            rr_scores = self.transport.rerank(query, docs)

            scored: list[tuple[Candidate, float, dict]] = []
            for (cand, _cos), rr in zip(top, rr_scores):
                strength = self.policy.strength(
                    cand.decay_class, cand.s0, cand.t0, now, status=cand.status
                )
                mult = self.policy.multiplier(
                    cand.decay_class, cand.needs_confirmation
                )
                rr_cal = RERANK_FLOOR + (1.0 - RERANK_FLOOR) * rr
                value = rr_cal * strength * mult
                rendered = self._render_card(cand, bed, retired_by_entity)
                scored.append((cand, value, rendered))

            scored.sort(key=lambda t: (-t[1], t[0].id))

            # duplicate-thread suppression: drop candidates whose citations
            # are a subset of a stronger candidate's citations
            kept: list[tuple[Candidate, float, dict]] = []
            for cand, value, rendered in scored:
                cites = set(rendered["citations"])
                if any(cites <= set(k[2]["citations"]) for k in kept):
                    left_out.append(
                        LeftOutItem(
                            id=cand.id,
                            label=rendered["sbar"][:80],
                            reason="duplicate_thread",
                            value=round(value, 4),
                            tokens=rendered["tokens"],
                        )
                    )
                    continue
                kept.append((cand, value, rendered))

            packer = BudgetPacker(budget=budget, max_items=max_cards)
            pack_result = packer.pack(
                [
                    PackCandidate(
                        id=cand.id,
                        value=round(value, 6),
                        tokens=rendered["tokens"],
                        label=rendered["sbar"][:80],
                        payload=rendered,
                    )
                    for cand, value, rendered in kept
                ]
            )
            for pc, reason in pack_result.left_out:
                left_out.append(
                    LeftOutItem(
                        id=pc.id, label=pc.label, reason=reason,
                        value=round(pc.value, 4), tokens=pc.tokens,
                    )
                )

            # optional live-LLM prose rewrite for selected cards; the template
            # remains the fallback and the budget stays enforced
            for pc in pack_result.selected:
                rendered = pc.payload
                prose = self.transport.brief_prose(
                    {
                        "facts": rendered["sbar"],
                        "why": rendered["why_tonight"],
                        "bed": bed,
                    }
                )
                if prose and isinstance(prose, dict) and prose.get("sbar"):
                    new_tokens = (
                        approx_tokens(str(prose["sbar"]))
                        + approx_tokens(str(prose.get("why_tonight", "")))
                        + approx_tokens(rendered["decay_note"] or "")
                        + sum(approx_tokens(f"[{c}]") for c in rendered["citations"])
                    )
                    delta = new_tokens - rendered["tokens"]
                    if pack_result.total_tokens + delta <= budget:
                        rendered["sbar"] = str(prose["sbar"])
                        rendered["why_tonight"] = str(
                            prose.get("why_tonight", rendered["why_tonight"])
                        )
                        rendered["tokens"] = new_tokens
                        pack_result.total_tokens += delta

            tokens_by_source: dict[str, int] = {}
            for ix, pc in enumerate(pack_result.selected, start=1):
                rendered = pc.payload
                tokens_by_source[rendered["source_id"]] = rendered["tokens"]
                cards.append(
                    BriefCard(
                        bed=bed,
                        priority=ix,
                        sbar=rendered["sbar"],
                        why_tonight=rendered["why_tonight"],
                        citations=rendered["citations"],
                        decay_note=rendered["decay_note"],
                        needs_confirmation=rendered["needs_confirmation"],
                        source_id=rendered["source_id"],
                    )
                )
            token_count = pack_result.total_tokens
        else:
            tokens_by_source = {}

        # mechanical gate — I1/I2: never ship uncited or dead-source cards
        validator = CitationValidator(
            lambda cid: self.store.status_at(cid, as_of_shift)
        )
        result = validator.validate(cards)
        cards = [
            c.model_copy(update={"priority": i + 1})
            for i, c in enumerate(result.valid)
        ]
        if result.rejected:
            # recompute the budget meter from surviving cards only
            token_count = sum(
                tokens_by_source.get(c.source_id, 0) for c in cards
            )

        brief = Brief(
            bed=bed,
            as_of_shift=as_of_shift,
            for_shift=as_of_shift + 1,
            generated_at=now,
            engine="live" if self.transport.name == "live" else "fake",
            budget=budget,
            token_count=token_count,
            cards=cards,
            retired=retired,
            left_out=left_out,
            routine_expired_count=self.store.routine_expired_count(bed, as_of_shift),
        )
        assert brief.token_count <= budget, "I3 violated: brief over budget"
        return brief
