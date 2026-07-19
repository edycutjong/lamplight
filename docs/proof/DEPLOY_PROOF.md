# Alibaba Function Compute — deployment proof (LIVE)

> **SYNTHETIC DATA ONLY.** No real patients, no PHI. Research prototype.

**STATUS: DEPLOYED & LIVE** on Alibaba Function Compute 3.0, managed
`python3.10` runtime (no container, no ACR, no real-name verification).

- **Live URL:** https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run
- **Region:** ap-southeast-1 (Singapore)
- **Function:** `lamplight` (functionArn `acs:fc:ap-southeast-1:5640684230009202:functions/lamplight`)
- **Runtime:** managed `python3.10`, handler `infra.fc.wsgi.handler` (event handler, not WSGI)
- **Trigger:** anonymous HTTP (GET + POST)
- **Deployed:** 2026-07-19

Lamplight targets Python 3.12 (`enum.StrEnum`, `datetime.UTC`); the managed
runtime is 3.10, so `infra/fc/wsgi.py` shims both symbols before importing the
package. Everything below runs **offline, zero-key, zero-network** on the
deterministic FakeQwen transport.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/verify` | socket-guarded byte-identical replay + signed op-chain verify (I4 + I5) |
| GET | `/run` | one deterministic offline handover brief (`?bed=&shift=&budget=`) |

## Live curl outputs

### `GET /health` → 200

```json
{
  "status": "ok"
}
```

### `GET /verify` → 200

Socket guard installed for the replay (any network call raises); the ward is
rebuilt from committed fixtures, the Bed-9 shift-15 hero brief is byte-compared
to the committed expected JSON (I5), and the Ed25519 op ledger is verified (I4).

```json
{
  "byte_identical": true,
  "chain": {
    "ok": true,
    "ops_by_type": {
      "consolidate": 50,
      "contradict": 1,
      "decay": 15,
      "expire": 12,
      "write": 109
    },
    "pubkey": "ab0bf2d3d8db3c92...",
    "signed_ops": 187
  },
  "detail": "brief byte-identical (2260 bytes); chain ok (187 signed ops)",
  "expected": "brief_bed9_shift15.json",
  "invariants": {
    "I4_signed_op_chain": true,
    "I5_byte_identical_replay": true
  },
  "network": "BLOCKED (socket guard installed for replay)",
  "overall": "PASS",
  "source": "offline FakeQwen replay of committed ward fixtures (zero key, zero network)"
}
```

### `GET /run?bed=9&shift=15` → 200

The `lamplight demo` equivalent: ingest all 15 fixture shifts into a throwaway
ward, then build the Bed-9 shift-15 SBAR brief. Card #1 is the cefazolin thread
stitched (and cited) across shifts s04→s06→s12; the resolved IV-site concern is
visibly retired; budget reads **334 / 2000 tokens**.

```
token_count: 334 / 2000
signed_ops:  187
num_cards:   4  (priority #1 cefazolin thread, citations ep-09-04-1 / -06-1 / -12-1)
routine_expired_count: 10
retired: [
  {
    "at_shift": 2,
    "citation": "ep-09-02-1",
    "label": "IV site left forearm slightly red at the hub, flushing well - watching.",
    "reason": "resolved"
  }
]
```

## Reproduce

```bash
export PATH="$HOME/.local/bin:$PATH"
cd build/infra/fc
s build --use-docker      # installs requirements.txt into ./python (3.10 wheels)
s deploy -y               # provisions the function + anonymous HTTP trigger

U=https://lamplight-asvskcmpbg.ap-southeast-1.fcapp.run
curl "$U/health"
curl "$U/verify"
curl "$U/run?bed=9&shift=15"
```

Deploying changes no bench number and no test outcome — the memory engine is the
product; Function Compute is only its runtime.
