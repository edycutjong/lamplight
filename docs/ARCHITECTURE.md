# Architecture: Lamplight

> Diagram: see the README's architecture section. Memory design, data model, and
> crypto/econ extensions live in the project's internal design spec (not shipped
> in this repo).

## Stack
| Layer | Choice | Why |
|---|---|---|
| API/worker | Python FastAPI on **Alibaba Function Compute** | deployment proof; stateless brief-builds |
| Memory store | Supabase Postgres + pgvector | episodes/memories/briefs; RLS-ready |
| UI | Next.js (`npx create-next-app`; no catalog match) | timeline + brief view |
| Crypto | pynacl (Ed25519 op-chain, SealedBox episodes) | audit + privacy primitives |
| Packaging | pip `lamplight-memory` + typer CLI | Layer-3 complexity; domain-agnostic reuse |

## API Endpoints
`POST /episodes` (note/voice ingest) · `POST /shifts/{n}/close` (trigger consolidation Batch) · `GET /briefs/{bed}?budget=2000` · `POST /feedback` (confirm/correct/dismiss) · `GET /audit/chain` + `GET /integrations/verify` (chain check, op feed, bench summary).

## Model Selection (domain justification)
| Model / feature | Why THIS one | What a generic choice would miss |
|---|---|---|
| `fun-asr` (diarization) | handovers are two-speaker events — attributing "watch that rash" to the outgoing nurse vs the charge nurse changes its weight | generic ASR merges speakers; attribution-free memories can't be trusted or audited |
| `qwen3.7-plus` (extraction + brief) | clinical-register comprehension at a price that allows per-note calls all day | flash misreads negations ("no rash" → rash); max is 6× the cost for marginal gain here |
| `text-embedding-v4` + `qwen3-rerank` (two-stage) | recall@40 cheap, then precision@5 where it counts — the budget packer needs *ranked truth*, not similarity soup | single-stage vector search is exactly the naive-RAG baseline we beat by 0.37 recall |
| structured output (Episode/BriefCard) | briefs drive care decisions; uncited or malformed cards are rejected mechanically | free-text briefs can't be validated, cited, or token-budgeted |
| function calling (memory ops) | decay/contradict/pin are typed, signed, auditable state transitions | prompt-side "please forget" is neither timely nor provable |
| Batch API (consolidation) | nightly merge across 6×15 episode sets at −50% — the $/patient-day metric depends on it | live-priced consolidation doubles the operating cost we advertise |
| `qwen3.7-max` (seed generation only, disclosed) | synthetic ward needs arc coherence across 15 shifts | weaker generators produce threads the bench can't ground-truth |

## Data Model
Episodes/memories/briefs tables (see `src/lamplight_memory/store.py`) + `op_chain(seq, op, payload_hash, prev_hash, sig)` + `envelopes(episode_id, sealed_blob, key_ref)`.

## Boilerplate
`npx create-next-app web` + `uv init memory/`; vendor `qwenkit/`.

## Residual Risk (honest)
Synthetic-data-only prototype — NOT a medical device (banner in-product); extraction misses degrade recall (bounded by bench, published); diarization errors on crosstalk flagged low-confidence rather than silently attributed.
