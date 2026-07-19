# Alibaba Function Compute — deployment proof

**STATUS: DEPLOYED LIVE.** Lamplight is deployed on **Alibaba Function Compute**
(managed `python3.10` runtime — no container, no image registry) via
[`s.yaml`](./s.yaml) + [`wsgi.py`](./wsgi.py):

**`https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run`**

| Endpoint | What it does | Verify |
|---|---|---|
| `GET /health` | liveness → `{"status":"ok"}` | `curl .../health` |
| `GET /verify` | socket-guarded byte-identical replay + signed op-chain verify (I4/I5) — the invariant proof, running in the cloud | `curl .../verify` |
| `GET /run?bed=9&shift=15` | one deterministic offline handover brief (FakeQwen, no key) | `curl ".../run?bed=9&shift=15"` |

The deployed and graded path is the **offline-deterministic engine** (FakeQwen,
byte-for-byte replayable). The live Qwen Cloud path (`qwen3.7-plus` +
`text-embedding-v4` + `qwen3-rerank` + `fun-asr`) is wired and **verified with a
real DashScope call** (smoke); a full captured live run is key-gated.

## What IS proven, offline and reproducibly

Lamplight's substantive claims do **not** depend on the hosting. They are all
verifiable with zero keys and zero network (and the same `/verify` proof runs in
the cloud):

| Claim | How to verify | Artifact |
|---|---|---|
| Deterministic rebuild (I5) | `python scripts/verify_offline.py` | byte-identical hero brief |
| Signed op-chain (I4) | same script + `lamplight verify-chain` | 187 Ed25519-signed ops |
| Recall vs naive RAG | `python memory_bench.py` | `bench_results/RESULTS.md` |
| 458 passing tests | `pytest` | green suite |

## Deploy path (managed python3.10 runtime)

```bash
npm i -g @serverless-devs/s
export ALIBABA_CLOUD_ACCESS_KEY_ID=...      # not committed
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
cd build/
s deploy                                    # provisions fn + HTTP trigger
curl "$FC_URL/verify"                        # chain report + invariant proof
```

Deploying does not change any number in the bench or any test outcome — the
memory engine is the product; Function Compute is only its runtime.
