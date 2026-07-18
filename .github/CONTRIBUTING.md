# Contributing

Thanks for your interest in improving Lamplight!

## Getting Started
1. Fork the repo and branch from `main`: `git checkout -b feat/your-feature`
2. Create a venv and install dev dependencies: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
3. (Optional) Copy the env template: `cp .env.example .env` — only needed for the live Qwen transport; everything else runs offline with zero keys.
4. Run the offline verification: `python scripts/verify_offline.py`

## Before You Open a PR
- `ruff check .` passes.
- `mypy .` passes (or documents new `continue-on-error` cases).
- `pytest --cov=src -q` passes — all 458+ tests green.
- `python scripts/verify_offline.py` passes (no network, no API key).
- Add or update tests for any behavior change, especially around the invariants (I1-I5) in `tests/test_invariants.py`.
- Keep commits conventional (`feat:`, `fix:`, `docs:`, `chore:`).

## Reporting Bugs / Requesting Features
Open an issue using the provided templates. Include repro steps, expected vs.
actual behavior, and environment details.
