# Lamplight memory bench — results

> Engine: **fake** transport. Offline deterministic run: FakeQwen surface-form hash embeddings (NOT text-embedding-v4) — separation comes from memory architecture (consolidation/decay/criticality), not embedding quality; live mode re-runs this bench on real embeddings. Baseline = naive top-5 cosine over the same embeddings and query.

## Critical-item recall@5 per shift

| Incoming shift | Ground-truth items | Lamplight | Naive RAG |
|---:|---:|---:|---:|
| 3 | 3 | 1.00 | 1.00 |
| 4 | 3 | 1.00 | 1.00 |
| 5 | 3 | 1.00 | 1.00 |
| 6 | 3 | 1.00 | 1.00 |
| 7 | 4 | 1.00 | 1.00 |
| 8 | 5 | 1.00 | 0.80 |
| 9 | 5 | 1.00 | 0.80 |
| 10 | 5 | 1.00 | 0.80 |
| 11 | 5 | 1.00 | 0.80 |
| 12 | 5 | 1.00 | 0.80 |
| 13 | 6 | 1.00 | 0.67 |
| 14 | 6 | 1.00 | 0.67 |
| 15 | 6 | 0.83 | 0.67 |
| **mean** |  | **0.99** | **0.85** |

## Planted-thread recall rate (share of active shifts recalled)

| Thread | Lamplight | Naive RAG | First surfaced (L/B) |
|---|---:|---:|---|
| cefazolin-reaction | 1.00 | 0.67 | s7 / s7 |
| falls-risk | 1.00 | 0.00 | s8 / s— |
| penicillin-allergy | 1.00 | 1.00 | s3 / s3 |
| seizure-precautions | 1.00 | 1.00 | s3 / s3 |
| sleep-conflict | 0.67 | 1.00 | s13 / s13 |
| warfarin-bleeding-risk | 1.00 | 1.00 | s3 / s3 |

## Safety + budget metrics

- **Forgetting precision:** 1.00 (0 violations across 78 briefs)
- **Baseline surfaced resolved/expired items:** 151 times (naive RAG never forgets)
- **Citation validity:** 1.00
- **Token compliance:** 100% of briefs <= budget (max observed 418 tokens)

## Cost estimate (PLACEHOLDER prices — see pricing.py)

- **$/patient-day (estimate): $0.0008** (6 patients x 5 days; heuristic ~4 chars/token counts x ASSUMED unit prices; consolidation priced at Batch -50%). Replace `ASSUMED_PRICES_PER_MTOK` with console prices before quoting.

| Surface | tokens | est. USD |
|---|---:|---:|
| qwen3-rerank | 187,200 | $0.0094 |
| qwen3.7-plus:input | 35,441 | $0.0071 |
| qwen3.7-plus:output | 13,329 | $0.0080 |
| text-embedding-v4 | 13,103 | $0.0009 |

_All bench floors hold: recall floor, separation floor, forgetting precision 1.0, citation validity 1.0, token compliance 100%._
