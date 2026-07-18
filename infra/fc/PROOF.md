# Alibaba Function Compute — deployment proof

**STATUS (honest): NOT deployed in this build.** The API is runnable locally
(`uvicorn api.main:app`) and the deployment is fully scaffolded in
[`s.yaml`](./s.yaml), but no live Function Compute endpoint was provisioned in
this timebox. This file is the placeholder the submission's "Alibaba proof"
checklist item points at; it will hold the console recording + live URL once
deployed.

## What IS proven, offline and reproducibly

Lamplight's substantive claims do **not** depend on the hosting. They are all
verifiable with zero keys and zero network:

| Claim | How to verify | Artifact |
|---|---|---|
| Deterministic rebuild (I5) | `python scripts/verify_offline.py` | byte-identical hero brief |
| Signed op-chain (I4) | same script + `lamplight verify-chain` | 187 Ed25519-signed ops |
| Recall vs naive RAG | `python memory_bench.py` | `bench_results/RESULTS.md` |
| 458 passing tests | `pytest` | green suite |

## Intended deploy path (when credentials are available)

```bash
npm i -g @serverless-devs/s
export ALIBABA_CLOUD_ACCESS_KEY_ID=...      # not committed
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
cd build/
s deploy                                    # provisions fn + HTTP trigger
s invoke -e '{}'                            # smoke test
curl "$FC_URL/integrations/verify"          # chain report + bench summary
```

## To attach once live (submission checklist)

- [ ] FC HTTP-trigger URL (paste here)
- [ ] Console screen recording of a `GET /briefs/9?shift=15` invocation + logs
- [ ] `GET /integrations/verify` JSON showing the signed chain + bench summary

Deploying does not change any number in the bench or any test outcome — the
memory engine is the product; Function Compute is only its runtime.
