"""examples/support_handover.py — the SAME memory engine, a non-clinical shift.

Support teams hand off too: the overnight on-call inherits a queue and a
two-line summary, and the ticket that mattered — "the payments 500s are the new
deploy, not the CDN" — never survives the handover. Lamplight's engine is
domain-agnostic. Swap patients for queues and shift notes for ticket updates;
the critical item persists, routine noise decays, and every briefed line still
cites its source. Nothing else changes.

    python examples/support_handover.py
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from lamplight_memory.engine import LamplightEngine
from lamplight_memory.transport.fake import FakeQwen

# "beds" are support queues; episodes are handover facts extracted per shift.
EXTRACTION = {
    (1, 1): [{"id": "ep-01-01-1", "bed": 1, "shift": 1, "ts": "", "type": "observation",
              "text": "Payments 500s began right after the 14:00 deploy, not the CDN — "
                      "suspect the new retry config.",
              "entities": ["payments_incident"], "decay_class": "critical",
              "why_hint": "roll back the deploy first if 500s resume tonight"}],
    (1, 2): [{"id": "ep-01-02-1", "bed": 1, "shift": 2, "ts": "", "type": "observation",
              "text": "Cleared the billing export backlog; queue back to normal.",
              "entities": ["billing_backlog"], "decay_class": "routine"}],
}

with TemporaryDirectory() as tmp:
    root = Path(tmp)
    for shift in (1, 2):                                    # one queue note per shift
        (root / "notes" / f"shift_{shift:02d}").mkdir(parents=True)
        (root / "notes" / f"shift_{shift:02d}" / "bed_01.txt").write_text(f"queue 1 s{shift}")
    engine = LamplightEngine(root / "support.db", FakeQwen(extraction_map=EXTRACTION), seal=True)
    for shift in (1, 2):
        engine.ingest_shift(shift, root / "notes" / f"shift_{shift:02d}")
    brief = engine.brief(bed=1, as_of_shift=2)              # hand queue 1 to the next shift
    print(f"Handover brief — queue 1 ({brief.token_count}/{brief.budget} tokens)\n")
    for card in brief.cards:
        print(f"#{card.priority} [{' '.join('[' + c + ']' for c in card.citations)}] {card.sbar}")
    engine.verify_chain()  # every op is signed and hash-chained, same as the clinical build
    engine.close()
