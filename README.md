<div align="center">
  <img src="docs/icon.svg" alt="Lamplight" width="144" height="144" />
  <h1>🏮 Lamplight</h1>
  <p><em>The night-shift memory that never clocks out — a cross-shift clinical memory agent that briefs the incoming nurse on the five things that will go wrong tonight, cited and budgeted.</em></p>
  <img src="docs/readme-hero.svg" alt="Lamplight — the night-shift memory that never clocks out" width="100%" />

  <br/><br/>

  [![Live](https://img.shields.io/badge/%F0%9F%8F%AE_Live-lamplight.edycu.dev-06b6d4?style=for-the-badge)](https://lamplight.edycu.dev)
  [![Live on Alibaba Function Compute](https://img.shields.io/badge/Alibaba_Function_Compute-Deployed-FF6A00?style=for-the-badge&logo=alibabacloud&logoColor=white)](https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run/health)
  [![Watch Demo](https://img.shields.io/badge/%E2%96%B6_Watch-Demo_Video-FF0000?style=for-the-badge)](https://youtu.be/Pyy5bAwCCVM)
  [![Devpost](https://img.shields.io/badge/Devpost-Submission-003E54?style=for-the-badge&logo=devpost)](https://devpost.com/software/lamplight-5z8f03)
  [![Pitch Deck](https://img.shields.io/badge/%F0%9F%93%BD%EF%B8%8F_Pitch-Deck-f59e0b?style=for-the-badge)](https://lamplight.edycu.dev/pitch/)
  [![Demo Path](https://img.shields.io/badge/%F0%9F%95%B9%EF%B8%8F_Judge-Demo_Path-F59E0B?style=for-the-badge)](DEMO.md)
  [![QwenCloud Hackathon](https://img.shields.io/badge/QwenCloud-Track_1_MemoryAgent-8b5cf6?style=for-the-badge)](https://qwencloud-hackathon.devpost.com/)

  <br/>

  ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat&logo=python&logoColor=white)
  ![Tests](https://img.shields.io/badge/tests-458_passing-success?style=flat)
  ![Coverage](https://img.shields.io/badge/coverage-100%25-success?style=flat)
  ![Offline](https://img.shields.io/badge/demo-offline%2C_zero_keys-blue?style=flat)
  [![License: MIT](https://img.shields.io/badge/License-MIT-06b6d4)](LICENSE)
  [![CI](https://github.com/edycutjong/lamplight/actions/workflows/ci.yml/badge.svg)](https://github.com/edycutjong/lamplight/actions/workflows/ci.yml)
</div>

**Track 1 · MemoryAgent.** A cross-shift clinical memory agent: it ingests every
nursing shift's notes into per-patient episodic memory, **consolidates and
decays** ("IV site check — resolved" visibly retires), and briefs the incoming
nurse on the five things that will go wrong tonight — in a hard **2,000-token
budget**, every item **citing its source episode**, every memory operation a
**signed, hash-chained ledger entry**.

> *A night nurse inherits 14 patients and a six-minute verbal handover. The one
> sentence that mattered — the rash started four hours after the new antibiotic
> — never makes it past shift change. At 3 AM it's anaphylaxis.*

Lamplight is the track text made literal: **efficient storage/retrieval**
(episodic store), **timely forgetting** (decay classes + resolution retirement),
and **recall within a limited context window** (the budgeted, cited SBAR brief).

---

> ## ⚠️ SYNTHETIC DATA ONLY
> The entire ward — 6 patients × 15 shifts — is **hand-authored synthetic
> fixture data**. **No real patients, no PHI.** Lamplight is a **research
> prototype, not a medical device**, and makes no clinical claims. Names,
> vitals, and events are invented for a benchmark.

---

## 📊 The bench: recall, not vibes

`memory_bench.py` replays the synthetic 5-day ward and scores **critical-item
recall@5 per shift** against a naive top-k RAG baseline over the *same*
embeddings and *same* query, plus forgetting precision and citation validity.
The committed run (`bench_results/RESULTS.md`, regenerate with `python
memory_bench.py`):

| Metric | **Lamplight** | Naive RAG |
|---|---:|---:|
| **Mean critical-item recall@5** | **0.99** | 0.85 |
| Forgetting precision (0 retired items surfaced) | **1.00** | — |
| Retired items resurfaced across 78 briefs | **0** | **151** |
| Citation validity | **1.00** | — |
| Token compliance (≤ 2,000) | **100%** (max 418) | — |
| $/patient-day (placeholder prices) | **~$0.0008** | — |

### Where the memory actually earns its keep — planted threads

| Thread | Lamplight | Naive RAG | Why |
|---|---:|---:|---|
| **falls-risk** (one buried clause) | **1.00** | **0.00** | vocabulary gap: "unsteady to the bathroom" ≠ "falls risk" |
| **cefazolin-reaction** (3 phrasings) | **1.00** | 0.67 | consolidation stitches erythema / red patches / rash into one thread |
| penicillin-allergy | 1.00 | 1.00 | stated plainly — naive RAG finds it too (honest) |
| seizure-precautions | 1.00 | 1.00 | stated plainly |
| warfarin-bleeding-risk | 1.00 | 1.00 | stated plainly |

**The honest story:** naive RAG is *legitimately competitive* on facts written
in query-matching words. Lamplight's edge is decisive exactly where memory
architecture matters — the **vocabulary-gap / buried threads** it recalls every
shift and the baseline misses, and **forgetting**: Lamplight never cites a
resolved item; the baseline resurfaced retired items **151 times**. (The SPEC's
aspirational "0.92 vs 0.55" headline was not chased on the frozen fixture — see
[Spec deviations](#spec-deviations) and `docs/friction-log.md §2`.)

## 🚀 Quickstart (offline, zero keys, zero network)

```bash
cd build/
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

pytest -q                         # 458 passing, ~45s
python scripts/verify_offline.py  # network-off replay + chain verify (I4/I5)
python memory_bench.py            # regenerate the recall table
lamplight demo                    # the hero brief in one shot (watch it forget the IV item)
lamplight replay                  # byte-identical rebuild + chain verify
```

**Tests: 458 passing, 100% src coverage.** Everything above runs on the deterministic FakeQwen
transport — no `DASHSCOPE_API_KEY`, no sockets (proven by the socket guard in
`scripts/verify_offline.py`).

## 🧠 The memory design (the actual product)

- **Episode** — one extracted clinical fact: `{bed, shift, ts, type, text,
  entities, polarity, decay_class, status, strength}`.
- **Decay classes with real half-life math** — `strength(t) = s₀·2^(−Δt/λ)`:
  - `critical` (allergy-suspect, falls-risk) — **never decays** until explicitly
    resolved + confirmed;
  - `condition` — λ = **72 h**;  `routine` — λ = **8 h** (one shift);
  - `resolved` — retired immediately (history only).
  A human confirmation bumps `s₀` by +0.25 and resets the clock; items below
  `strength 0.05` are swept by a signed `expire` op. *(`decay.py`)*
- **Consolidation** — at each night close, same-entity episodes merge into a
  versioned semantic memory with a full **provenance list** (the IDs the brief
  cites); merged class = highest criticality. *(`consolidate.py`)*
- **Contradiction flags** — opposite-polarity reports on one entity ("slept
  well" vs "up 4× overnight") become a `needs_confirmation` memory, priced as
  critical so it can't silently decay out. *(`contradiction.py`)*
- **Budget knapsack** — retrieve top-40 → rerank → value = `rerank ×
  decay_strength × criticality` → greedy-pack into 2,000 tokens, **logging what
  it left out and why**. The #1 safety item is never dropped for two cheaper
  ones. *(`packer.py`, `brief.py`)*
- **Mechanical citation validator** — a card citing nothing, or a
  resolved/expired source, is **rejected**, never patched. *(`validator.py`)*

### Tested invariants (I1–I5)

| | Invariant | Test |
|---|---|---|
| **I1** | Every brief item cites ≥ 1 existing, **active** episode | `test_invariants.py::test_I1_*` |
| **I2** | **Zero** resolved/expired items in any brief (forgetting precision = 1.0) | `::test_I2_*` |
| **I3** | Every brief ≤ 2,000 tokens (hard-asserted) | `::test_I3_*` |
| **I4** | Op-chain verifies; any **1-byte tamper fails** | `::test_I4_*` |
| **I5** | Replayed fixtures → **byte-identical** briefs | `::test_I5_*` |

## 🧩 Why only Qwen Cloud

Take Qwen Cloud out and Lamplight is four vendors and a cron job — and the
recall-curve bench that separates it from every "chatbot with memory" would cost
too much to run.

| Qwen surface | Role | Without it |
|---|---|---|
| `fun-asr` (speaker-diarized) | voice-handover ingest, attributed to outgoing vs charge nurse | ASR vendor + a diarization pipeline; unattributed memories can't be audited |
| `qwen3.7-plus` | episode extraction + SBAR prose | flash-tier negation errors ("no rash" → rash) are clinical poison |
| `text-embedding-v4` | episodic store | embedding vendor at 2–4× price |
| `qwen3-rerank` | precision@5 before the packer | single-stage retrieval *is* the 0.85 baseline we beat |
| structured output | Episode/BriefCard schemas | the citation validator has nothing mechanical to check |
| function calling | signed memory ops | forgetting as cron, not typed auditable transitions |
| Batch API (−50%) | nightly consolidation | the $/patient-day economics double |

*(Model IDs used: `qwen3.7-plus`, `text-embedding-v4`, `qwen3-rerank`, `fun-asr`;
`qwen3.7-max` is used **only** for disclosed one-time seed-prose drafting, never
at runtime — `seed.py --llm`.)*

## 📦 Domain-agnostic: the engine ships as a package

`lamplight-memory` is not clinical — it's a shift-handover memory engine. The
same primitives rebuild as an on-call **support handover** in ~15 lines
(`examples/support_handover.py`): the critical "payments 500s are the new
deploy" incident persists and is cited; routine queue noise decays.

```python
from lamplight_memory.engine import LamplightEngine
from lamplight_memory.transport.fake import FakeQwen
engine = LamplightEngine("support.db", FakeQwen(extraction_map=FACTS), seal=True)
engine.ingest_shift(1, notes_dir); engine.ingest_shift(2, notes_dir)
brief = engine.brief(bed=1, as_of_shift=2)   # cited, budgeted, decayed
```

## 🏗️ Architecture

```mermaid
flowchart LR
  IN["notes / voice"] --> EX["extract"] --> SEAL["ECIES seal"] --> EP[("episodic store<br/>SQLite + cosine — text-embedding-v4")]
  EP --> NI["nightly: contradiction · consolidate (Batch −50%) · decay<br/>each op → Ed25519 hash-chained (I4)"]
  NI --> EP
  Q["handover query"] --> RET["top-40"] --> RR["qwen3-rerank"] --> PK["budget knapsack ≤2k tok (I3)"] --> CV["citation validator (I1–I2)"] --> BR["SBAR brief"]
  EP --> RET
  EX <--> TT{{"Qwen transport"}}
  TT --> FQ["FakeQwen — default, hash-embeddings, no key"]
  TT --> LQ["LiveQwen — qwen3.7-plus · text-embedding-v4 · qwen3-rerank · fun-asr"]
```

<sub>**As built** = offline runs on FakeQwen hash-embeddings (the bench separation comes from the memory architecture, not embedding quality); live mode uses real `text-embedding-v4` + `qwen3-rerank` behind `DASHSCOPE_API_KEY`. Store is SQLite offline / Supabase-pgvector in the deployed spec; **deployed live on Alibaba Function Compute** (`infra/fc/`, managed python3.10). Plain-text view below.</sub>

```
notes/voice ─▶ qwen3.7-plus extract ─▶ ECIES-seal ─▶ episodic store (text-embedding-v4)
                                                          │
                    nightly: contradiction ▸ consolidation (Batch −50%) ▸ decay sweep
                                                          │  (each op → Ed25519 signed, hash-chained)
      handover query ─▶ top-40 ─▶ qwen3-rerank ─▶ budget knapsack (≤2k) ─▶ citation validator ─▶ SBAR brief
```

Runtime: Alibaba Function Compute (`infra/fc/`, managed python3.10); store:
Supabase/pgvector in the deployed spec, SQLite offline. Full deployed topology:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## ☁️ Deployed — live on Alibaba Function Compute

Lamplight is **deployed live on Alibaba Function Compute** (managed
`python3.10` runtime — no container, no image registry):

**`https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run`**

| Endpoint | What it does |
|---|---|
| [`GET /health`](https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run/health) | liveness → `{"status":"ok"}` |
| [`GET /verify`](https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run/verify) | socket-guarded byte-identical replay + signed op-chain verify (I4/I5) — the invariant proof, running in the cloud |
| [`GET /run?bed=9&shift=15`](https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run/run?bed=9&shift=15) | one deterministic offline handover brief (FakeQwen, no key) |

The deployed and graded path is the **offline-deterministic engine** (FakeQwen,
byte-for-byte replayable) — `/verify` installs a socket guard and reproduces the
committed hero brief *in the cloud*. The live Qwen Cloud path (`qwen3.7-plus` +
`text-embedding-v4` + `qwen3-rerank` + `fun-asr`) is wired and **verified with a
real DashScope call** (smoke); a full captured live run is key-gated.

## 📋 Status — what's real, what's pending (honest)

**Landed and verified offline:**
- ✅ Full memory engine: episodic store, decay classes, consolidation,
  contradiction flags, budget packer, citation validator.
- ✅ **ECIES sealing at rest landed** — PyNaCl `SealedBox`; episode plaintext is
  NULL in the store, ciphertext in `envelopes`, unsealed only at brief-build
  (`sealed.py`; `test_engine.py::test_text_of_unseals`). *(Not dropped — the
  BUILD_PLAN drop-line was not reached.)*
- ✅ Ed25519 signed, hash-chained op ledger + `verify-chain` (I4).
- ✅ Deterministic seed ward + `memory_bench.py` recall curves + floors.
- ✅ `lamplight` CLI, `verify_offline.py`, `check_submission_readiness.py`.
- ✅ 458 passing tests, 100% `lamplight_memory` coverage.

**Landed:**
- ✅ **Deployed live on Alibaba Function Compute** (managed python3.10) at
  `https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run` — `/health`, `/verify`
  (socket-guarded replay + op-chain verify in the cloud), `/run` (handover
  brief). Scaffold + status in `infra/fc/`.

**Pending / behind a key / deferred:**
- ⏳ **Full live-Qwen run** (`text-embedding-v4`, `qwen3-rerank`, `qwen3.7-plus`,
  `fun-asr`): code path present in `transport/live.py`, runs behind
  `DASHSCOPE_API_KEY`. The live model path is wired and **verified with a real
  DashScope call** (smoke), but **no full captured live run** is in this build —
  the deployed and graded path is the offline-deterministic engine. Rerank +
  fun-asr request shapes are best-effort (`docs/friction-log.md §7`).
- ⏳ **Next.js timeline UI**: deferred. An optional static `web/brief.html`
  renderer of the hero brief is included; the full timeline/feedback UI is not
  built.
- ⏳ **Crypto-deletion** (per-episode envelope key destruction on expiry):
  documented as `[stretch]`, not implemented.

## 📐 Spec deviations

1. **Bench floors recalibrated to the honest fixture.** The SPEC/PRD headline
   "0.92 vs 0.55" was aspirational; the frozen ward yields **0.99 vs 0.85 mean**
   because the naive baseline is legitimately strong on plainly-worded facts.
   The floors now assert what's true and defensible — recall ≥ 0.95, mean
   separation ≥ 0.10, and *strict* per-thread separation on the engineered
   vocabulary-gap threads (falls 1.00 vs 0.00, cefazolin 1.00 vs 0.67). The
   bench still fails the build on regression. (`bench.py` `FLOORS`;
   `friction-log.md §2`.)
2. **Ground-truth tightened.** The cefazolin thread's evidence excludes the
   shift-4 med-start order (surfacing "cefazolin started" ≠ conveying the
   reaction); `seed.py --check` enforces fixture/source parity. (`§3`.)
3. **Next.js timeline UI deferred** as above — the memory engine and its bench
   are the submission's spine, per BUILD_PLAN ("never cut: bench, citations
   validator, decay/retire, replay"). Function Compute is now deployed live.

## ✅ Testing & CI

```bash
ruff check .                            # lint (clean)
mypy .                                  # types (advisory — LiveQwen's
                                        # OpenAI-shaped overloads + a
                                        # few Optional narrowings)
pytest --cov=src --cov-report=term -q   # 458 passing, 100% src coverage
python scripts/verify_offline.py        # network-off replay + chain verify
python -m build                         # sdist + wheel, CLI entrypoint installs
pip-audit                               # dependency vulnerability scan
```

| Layer | Tool | Status |
|---|---|---|
| Code Quality | ruff | ✅ clean |
| Type Checking | mypy | ⚠️ advisory (see above) |
| Unit Testing | pytest (458 tests, 100% coverage) | ✅ |
| Offline Invariant Verify | `scripts/verify_offline.py` (I1–I5, zero network) | ✅ |
| Package Build | `python -m build` (sdist + wheel) | ✅ |
| Security (SAST) | CodeQL (`.github/workflows/codeql.yml`) | ✅ configured |
| Security (SCA) | Dependabot (`pip` + `github-actions`) + `pip-audit` | ✅ configured |
| Secret Scanning | TruffleHog (CI Stage 2) | ✅ configured |
| CI/CD Pipeline | GitHub Actions, 4-stage (Quality → Security → Build → Deploy Gate) | ✅ `.github/workflows/ci.yml` |

Env vars (all optional — everything above runs with none of them set) are
documented in [`.env.example`](./.env.example).

## 🗂️ Repo layout

```
build/
├── src/lamplight_memory/   engine, store, decay, consolidate, contradiction,
│                           packer, validator, brief, chain, sealed, bench, cli,
│                           clock, tokens, pricing, replay, transport/{fake,live}
├── tests/                  458 tests (test_decay, test_packer, test_invariants, …)
├── fixtures/ward_5day/     6 patients × 15 shifts: notes/, extraction/,
│                           ground_truth.json, expected/brief_bed9_shift15.json
├── bench_results/          RESULTS.md + summary.json (committed)
├── examples/support_handover.py     domain-agnostic reuse (~15 lines)
├── scripts/                verify_offline.py, check_submission_readiness.py
├── api/main.py             FastAPI app (FC-ready)
├── infra/fc/               s.yaml + wsgi.py + PROOF.md (deployed live on FC)
├── docs/friction-log.md    calibration + deviation notes
├── .github/                CI/CD, CodeQL, Dependabot, community health files
├── .env.example            documented optional env vars
├── seed.py  memory_bench.py  DEMO.md  README.md  LICENSE (MIT)
```

## 📄 License

MIT — see [`LICENSE`](./LICENSE). Built solo in a five-project sprint. Synthetic
data only; not a medical device.

## 🏷️ Versioning

This project uses [Semantic Versioning](https://semver.org) with **fully automated** version
management driven by [Conventional Commits](https://www.conventionalcommits.org) — the version is
never edited by hand.

| Commit type | Bump | Example |
|---|---|---|
| `fix: …` | patch | 1.0.0 → 1.0.1 |
| `feat: …` | minor | 1.0.0 → 1.1.0 |
| `feat!: …` or `BREAKING CHANGE:` footer | major | 1.0.0 → 2.0.0 |

[python-semantic-release](https://python-semantic-release.readthedocs.io) keeps the version in sync
across `pyproject.toml` and `src/lamplight_memory/__init__.py`.

- **In CI/CD:** Stage 6 of the pipeline (`.github/workflows/ci.yml`) runs on every push to `main`,
  computes the next version from the commits since the last tag, then commits + tags it automatically.
- **Locally:**
  ```bash
  pip install -e ".[release]"
  semantic-release version    # compute + apply the next version and tag
  ```

