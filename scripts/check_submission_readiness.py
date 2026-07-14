#!/usr/bin/env python3
"""check_submission_readiness.py — one command that answers "is Lamplight
submittable?" by re-running every honesty gate and listing what is missing.

Checks (all offline, deterministic):
  - required files present (README, LICENSE, pyproject, bench artifacts,
    expected brief, DEMO, friction log, api, infra/fc, examples);
  - fixtures are byte-identical to their hand-authored source (seed --check);
  - the pytest suite collects a meaningful number of tests;
  - the offline replay is byte-identical and the op chain verifies (I4/I5);
  - the memory bench holds all its floors (recall, separation, forgetting).

Exit 0 iff every gate passes.

    python scripts/check_submission_readiness.py
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def _required_files() -> None:
    required = [
        "README.md", "LICENSE", "pyproject.toml", "memory_bench.py", "seed.py",
        "DEMO.md",
        "bench_results/RESULTS.md", "bench_results/summary.json",
        "fixtures/ward_5day/ground_truth.json",
        "fixtures/ward_5day/expected/brief_bed9_shift15.json",
        "docs/friction-log.md",
        "examples/support_handover.py",
        "scripts/verify_offline.py",
        "api/main.py",
        "infra/fc/s.yaml", "infra/fc/PROOF.md",
    ]
    for rel in required:
        check((REPO / rel).exists(), f"file present: {rel}")


def _seed_check() -> None:
    import seed  # type: ignore

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = seed.check()
    check(rc == 0, "fixtures match hand-authored source (seed.py --check)")


def _tests_collect() -> None:
    import pytest

    class Collector:
        def __init__(self) -> None:
            self.count = 0

        def pytest_collectreport(self, report):  # noqa: ANN001
            pass

        def pytest_itemcollected(self, item):  # noqa: ANN001
            self.count += 1

    plugin = Collector()
    buf = io.StringIO()
    with redirect_stdout(buf):
        pytest.main(["--collect-only", "-q", str(REPO / "tests")], plugins=[plugin])
    check(plugin.count >= 100, "pytest suite >= 100 tests", f"{plugin.count} collected")


def _replay() -> None:
    from lamplight_memory.paths import find_fixtures
    from lamplight_memory.replay import replay

    result = replay(find_fixtures(None))
    check(
        result.ok and result.byte_identical and result.chain.ok,
        "offline replay byte-identical + chain verifies (I4/I5)",
        f"{result.chain.length} signed ops",
    )


def _bench() -> None:
    from lamplight_memory.bench import run_bench
    from lamplight_memory.paths import find_fixtures

    report = run_bench(find_fixtures(None), out_dir=None)
    check(
        report.ok,
        "memory bench holds all floors",
        f"recall {report.lamplight_mean:.2f} vs {report.baseline_mean:.2f}, "
        f"forgetting {report.forgetting_precision:.2f}",
    )


def main() -> int:
    print("Lamplight — submission readiness\n" + "=" * 40)
    _required_files()
    _seed_check()
    _tests_collect()
    _replay()
    _bench()
    print("=" * 40)
    passed = sum(1 for ok, _ in RESULTS if ok)
    total = len(RESULTS)
    failed = [label for ok, label in RESULTS if not ok]
    print(f"{passed}/{total} checks passed")
    if failed:
        print("MISSING / FAILING:")
        for label in failed:
            print(f"  - {label}")
        return 1
    print("READY — every honesty gate passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
