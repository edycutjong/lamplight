# Lamplight — demo & judge guide

> **SYNTHETIC DATA ONLY.** No real patients, no PHI. Research prototype, not a
> medical device.

Everything below runs **offline, with zero keys and zero network** on the
deterministic FakeQwen transport.

## 0. Setup (30 seconds)

```bash
cd build/
python -m venv .venv && . .venv/bin/activate      # or use the committed .venv
pip install -e ".[dev]"
```

## 1. The one command a skeptic should run

```bash
python scripts/verify_offline.py
```

Installs a hard socket guard (any network call raises), rebuilds the entire
5-day ward from committed fixtures, regenerates the **Bed 9, shift-15** hero
brief, byte-compares it to the committed expected output (**I5**), and verifies
the Ed25519 hash-chained op ledger (**I4**). Exits 0 with `OFFLINE VERIFY PASS`.

## 2. The tests (the gate)

```bash
pytest -q          # 458 passing, ~45s
```

Covers decay half-life math, the budget packer under adversarial item sizes,
citation rejection, consolidation/contradiction, invariants I1–I5 (incl. a
1-byte tamper), replay determinism, and the bench-floor separation assertion.

## 3. The bench — recall, not vibes

```bash
python memory_bench.py            # writes bench_results/RESULTS.md + summary.json
```

| | Lamplight | Naive RAG |
|---|---:|---:|
| **Mean critical-item recall@5** | **0.99** | 0.85 |
| Falls-risk thread (buried mention) | **1.00** | 0.00 |
| Cefazolin reaction (3 phrasings) | **1.00** | 0.67 |
| Forgetting precision | **1.00** | — |
| Retired items resurfaced | **0** | 151 |

The baseline is honestly competitive on plainly-worded facts; Lamplight wins on
the vocabulary-gap threads and on forgetting.

## 4. The money shot — watch it forget on purpose

```bash
python -m lamplight_memory.cli demo    # or: lamplight demo
```

One command, no prior `ingest` needed: it builds a fresh 15-shift ward
(`lamplight-demo.db`) and prints the Bed-9 shift-15 hero brief.

Card **#1** is the cefazolin thread — *"rash began 4h after cefazolin start"* —
stitched from three notes across shifts 4→6→12 in three different phrasings
(erythema / red patches / rash), each **cited**. The **retired** panel shows the
resolved IV-site concern struck through (`~~IV site left forearm slightly
red~~ (resolved s2)`) — it is deliberately *not* in the brief, and never cites
it. Budget meter reads well under 2,000 tokens (334 tok).

> Prefer to drive the engine by hand? `lamplight ingest fixtures/ward_5day/notes/shift_04 --shift 4`
> (repeat for shifts 1–15) then `lamplight brief --bed 9 --shift 15 --db lamplight.db` does the
> same thing the long way. `lamplight demo` just wires those steps into one copy-paste.

## 5. The audit trail

```bash
lamplight replay          # rebuild + byte-compare + chain verify (I4/I5)
```

Then prove tamper-evidence: flip one byte in the `op_chain` table of any ward DB
and `lamplight verify-chain --db <db>` reports `payload hash mismatch`.

## 6. Domain-agnostic reuse (the engine is the product)

```bash
python examples/support_handover.py
```

The same engine, ~15 lines, applied to an on-call support handover: the critical
"payments 500s are the new deploy" incident persists and is cited; routine queue
noise decays. Swap patients for queues, nothing else changes.

## 7. The API (local; FC deployment scaffolded, not performed)

```bash
uvicorn api.main:app --port 9000
curl "http://localhost:9000/integrations/verify" | python -m json.tool
curl "http://localhost:9000/briefs/9?shift=15" | python -m json.tool
```

See `infra/fc/PROOF.md` for the honest deployment status.

## 8. Submission readiness

```bash
python scripts/check_submission_readiness.py
```

Re-runs every gate (files present, fixtures match source, tests collect, replay
byte-identical, bench floors hold) and prints a checklist.

---

### Demo video beat sheet (3:00)

`0:00` hook (six-minute handover, 3 AM anaphylaxis) → `0:25` 15 shifts of notes
accumulating on Bed 9 → `0:50` **"Brief me"**: the resolved IV item strikes
through on camera → `1:20` the cefazolin card + citation click-through to the
source note → `1:50` bench recall curve, Lamplight vs naive RAG, full screen →
`2:20` `verify_offline.py` running with the network off → `2:40` 1-byte tamper
fails `verify-chain` → `2:55` close: *"memory with mortality attached."*
