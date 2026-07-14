#!/usr/bin/env python3
"""memory_bench.py — recall@5 curves (Lamplight vs naive RAG), forgetting
precision, citation validity, token compliance, $/patient-day.

    python memory_bench.py                # offline, deterministic (FakeQwen)
    python memory_bench.py --live         # re-run on Qwen Cloud embeddings
    python memory_bench.py --out DIR      # where to write RESULTS.md

Thin wrapper over lamplight_memory.bench (also: `lamplight bench`).
Exits non-zero if any bench floor is violated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))

from lamplight_memory.bench import render_markdown, run_bench  # noqa: E402
from lamplight_memory.paths import find_fixtures  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=REPO / "bench_results")
    ap.add_argument("--live", action="store_true",
                    help="use LiveQwen (requires DASHSCOPE_API_KEY)")
    args = ap.parse_args()

    fixtures_root = find_fixtures(args.fixtures)
    transport = None
    if args.live:
        from lamplight_memory.transport import get_transport

        transport = get_transport("live")

    report = run_bench(fixtures_root, out_dir=args.out, transport=transport)
    print(render_markdown(report))
    print(f"(written to {args.out}/RESULTS.md and summary.json)")
    if not report.ok:
        print("BENCH FLOOR VIOLATIONS:", *report.floor_violations, sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
