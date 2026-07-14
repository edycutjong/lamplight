"""memory_bench — recall curves, forgetting precision, and the asserted floors.

The bench is the submission's spine: it must prove Lamplight beats naive RAG
on the engineered threads and never resurfaces retired items — deterministically.
"""

from __future__ import annotations

import json
import shutil

import pytest

import lamplight_memory.bench as bench_mod
from lamplight_memory.bench import BENCH_SHIFTS, FLOORS, BenchReport, render_markdown, run_bench
from lamplight_memory.store import MemoryStore


@pytest.fixture(scope="module")
def report(fixtures_root):
    return run_bench(fixtures_root, out_dir=None)


# --------------------------------------------------------------------------- #
# floors
# --------------------------------------------------------------------------- #


def test_all_floors_hold(report):
    assert report.floor_violations == []
    assert report.ok is True


def test_recall_floor(report):
    assert report.lamplight_mean >= FLOORS["lamplight_mean_recall_min"]


def test_separation_floor(report):
    assert report.lamplight_mean - report.baseline_mean >= FLOORS["recall_separation_min"]


def test_lamplight_beats_baseline(report):
    assert report.lamplight_mean > report.baseline_mean


def test_forgetting_precision_is_one(report):
    assert report.forgetting_precision == 1.0
    assert report.forgetting_violations == []


def test_citation_validity_is_one(report):
    assert report.citation_validity == 1.0
    assert report.citation_violations == []


def test_token_compliance_is_one(report):
    assert report.token_compliance == 1.0
    assert report.max_brief_tokens <= 2000


def test_brief_count(report):
    # 6 beds x 13 incoming shifts (3..15)
    assert report.n_briefs == 6 * len(list(BENCH_SHIFTS))


# --------------------------------------------------------------------------- #
# the engineered threads must SEPARATE the systems (the real claim)
# --------------------------------------------------------------------------- #


def test_cefazolin_thread_separates(report):
    rate = report.thread_recall_rate["cefazolin-reaction"]
    assert rate["lamplight"] == 1.0
    assert rate["lamplight"] > rate["baseline"]


def test_falls_risk_is_clean_vocabulary_gap_win(report):
    rate = report.thread_recall_rate["falls-risk"]
    assert rate["lamplight"] == 1.0
    assert rate["baseline"] == 0.0  # naive RAG never finds the buried mention


def test_engineered_threads_beat_baseline(report):
    for tid in ("cefazolin-reaction", "falls-risk"):
        rate = report.thread_recall_rate[tid]
        assert rate["lamplight"] > rate["baseline"], tid


# --------------------------------------------------------------------------- #
# forgetting contrast: naive RAG resurfaces retired items, Lamplight never does
# --------------------------------------------------------------------------- #


def test_baseline_resurfaces_retired_items(report):
    assert report.baseline_resolved_surfaced > 0


def test_lamplight_forgetting_beats_baseline(report):
    # Lamplight: 0 retired items cited; baseline: many
    assert len(report.forgetting_violations) == 0
    assert report.baseline_resolved_surfaced > len(report.forgetting_violations)


# --------------------------------------------------------------------------- #
# economics + determinism
# --------------------------------------------------------------------------- #


def test_cost_estimate_present(report):
    assert report.usd_per_patient_day >= 0.0
    assert report.cost_breakdown  # per-surface rows


def test_bench_is_deterministic(fixtures_root):
    a = run_bench(fixtures_root, out_dir=None).summary_dict()
    b = run_bench(fixtures_root, out_dir=None).summary_dict()
    assert a == b


def test_floor_constants_sane():
    assert FLOORS["forgetting_precision"] == 1.0
    assert FLOORS["citation_validity"] == 1.0
    assert FLOORS["token_compliance"] == 1.0
    assert 0.0 < FLOORS["recall_separation_min"] <= 1.0


# --------------------------------------------------------------------------- #
# out_dir artifacts (RESULTS.md / summary.json) + render_markdown
# --------------------------------------------------------------------------- #


def test_out_dir_writes_results_and_summary(fixtures_root, tmp_path):
    out_dir = tmp_path / "bench_out"
    report = run_bench(fixtures_root, out_dir=out_dir)
    results_md = (out_dir / "RESULTS.md").read_text(encoding="utf-8")
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert "Lamplight memory bench" in results_md
    assert "_All bench floors hold" in results_md  # no-violations branch
    assert summary["engine"] == report.engine_name


def test_render_markdown_handles_missing_recall_and_violations():
    # a hand-built report exercises formatting branches a clean, passing
    # bench run never touches: an unscored shift (n=0 -> "—" recall cells),
    # a thread with no recorded "first surfaced" shift for one system, and
    # the floor-violations bullet list.
    report = BenchReport(
        per_shift=[
            {"shift": 3, "items": 0, "lamplight_recall": None, "baseline_recall": None},
            {"shift": 4, "items": 2, "lamplight_recall": 1.0, "baseline_recall": 0.5},
        ],
        lamplight_mean=1.0,
        baseline_mean=0.5,
        forgetting_precision=0.98,
        forgetting_violations=["s4 bed9: cited resolved source ep-x"],
        baseline_resolved_surfaced=3,
        citation_validity=1.0,
        token_compliance=1.0,
        max_brief_tokens=500,
        n_briefs=2,
        thread_first_recall={"t1": {"lamplight": 4}},  # no "baseline" key -> "—"
        thread_recall_rate={"t1": {"lamplight": 1.0, "baseline": 0.5}},
        usd_per_patient_day=0.1234,
        cost_breakdown=[("qwen3.7-plus:input", 1000, 0.0512)],
        engine_name="fake",
        floor_violations=["synthetic floor violation for markdown coverage"],
    )
    md = render_markdown(report)
    assert "| 3 | 0 | — | — |" in md
    assert "s4 / s—" in md  # first_recall baseline missing -> em dash
    assert "## FLOOR VIOLATIONS" in md
    assert "synthetic floor violation for markdown coverage" in md
    assert "_All bench floors hold" not in md


# --------------------------------------------------------------------------- #
# defensive invariant-violation detection (citation validity / forgetting)
#
# The real 15-shift ward never breaks these invariants (that's the whole
# point of I1/I2) — this proves bench.py's own detection code actually
# flags a break, by forcing the store's exists()/status_at() answers wrong
# for exactly one call each, *after* the ward is fully built. Everything
# upstream of that point (ingestion, consolidation) is untouched.
# --------------------------------------------------------------------------- #


def test_bench_flags_citation_and_forgetting_violations(fixtures_root, monkeypatch):
    real_exists = MemoryStore.exists
    real_status_at = MemoryStore.status_at
    real_build_ward = bench_mod.build_ward
    state = {"armed": False, "exists_hit": False, "status_hit": False}

    def wrapped_build_ward(engine, fx_root):
        real_build_ward(engine, fx_root)
        state["armed"] = True  # only corrupt reads made AFTER ingestion

    def fake_exists(self, item_id):
        if state["armed"] and not state["exists_hit"]:
            state["exists_hit"] = True
            return False
        return real_exists(self, item_id)

    # Each citation's status is checked twice per bed: once by the brief's
    # own CitationValidator (I1/I2, during engine.brief()) and again by
    # bench's own redundant safety check. A real store never disagrees
    # between those two calls (nothing mutates in between) — so to prove
    # bench's *own* check actually catches a disagreement, only tamper the
    # second lookup for whichever citation id first gets checked twice.
    # The first (validator) call still sees the true, active status, so the
    # card legitimately makes it into brief.cards for bench to re-check.
    status_call_counts: dict[str, int] = {}

    def fake_status_at(self, item_id, as_of):
        if state["armed"] and not state["status_hit"]:
            result = real_status_at(self, item_id, as_of)
            if result is not None:
                status_call_counts[item_id] = status_call_counts.get(item_id, 0) + 1
                if status_call_counts[item_id] == 2:
                    state["status_hit"] = True
                    from lamplight_memory.schemas import Status

                    return Status.RESOLVED
            return result
        return real_status_at(self, item_id, as_of)

    # also force the recall/token floors to fail so their append branches
    # run too, without needing to fabricate a bad ward.
    impossible_floors = dict(FLOORS)
    impossible_floors["lamplight_mean_recall_min"] = 999.0
    impossible_floors["recall_separation_min"] = 999.0
    impossible_floors["token_compliance"] = 999.0

    monkeypatch.setattr(bench_mod, "build_ward", wrapped_build_ward)
    monkeypatch.setattr(MemoryStore, "exists", fake_exists)
    monkeypatch.setattr(MemoryStore, "status_at", fake_status_at)
    monkeypatch.setattr(bench_mod, "FLOORS", impossible_floors)

    report = run_bench(fixtures_root, out_dir=None)

    assert state["exists_hit"] and state["status_hit"]
    assert report.citation_violations
    assert report.forgetting_violations
    assert report.citation_validity == 0.0
    assert report.forgetting_precision < 1.0
    assert report.ok is False
    joined = " | ".join(report.floor_violations)
    assert "lamplight mean recall" in joined
    assert "separation" in joined
    assert "forgetting precision" in joined
    assert "citation validity" in joined
    assert "token compliance" in joined


# --------------------------------------------------------------------------- #
# a citation that ground truth marks as "retired" (expiry) is a forgetting
# violation — exercised via a fixtures copy whose ground_truth.json is
# edited to (falsely, but harmlessly for this test) label an always-cited
# episode as retired. The committed fixtures directory is never touched.
# --------------------------------------------------------------------------- #


def _copied_fixtures_with_gt_edit(fixtures_root, tmp_path, edit_fn, name="fx_copy"):
    copy_root = tmp_path / name
    shutil.copytree(fixtures_root, copy_root)
    gt_path = copy_root / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    edit_fn(gt)
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    return copy_root


def test_bench_flags_forgetting_violation_for_expiry_marked_citation(fixtures_root, tmp_path):
    def edit(gt):
        gt["expiry"].append(
            {
                "bed": 9,
                "episodes": ["ep-09-06-1"],  # a real, reliably-cited cefazolin episode
                "label": "synthetic: falsely marked retired for coverage",
                "must_not_surface_from_shift": 7,
                "resolved_at_shift": 6,
                "thread": "synthetic-expiry-test",
            }
        )

    copy_root = _copied_fixtures_with_gt_edit(fixtures_root, tmp_path, edit)
    report = run_bench(copy_root, out_dir=None)
    assert report.forgetting_violations
    assert any("cited retired episode ep-09-06-1" in v for v in report.forgetting_violations)
    assert report.ok is False


# --------------------------------------------------------------------------- #
# engineered threads absent from ground truth (a non-clinical fixtures reuse)
# -> the extra floor checks are skipped gracefully, not KeyError'd
# --------------------------------------------------------------------------- #


def test_bench_skips_engineered_thread_checks_when_absent(fixtures_root, tmp_path):
    def edit(gt):
        drop = {"cefazolin-reaction", "falls-risk"}
        gt["threads"] = [t for t in gt["threads"] if t["id"] not in drop]
        for shift, items in gt["per_shift"].items():
            gt["per_shift"][shift] = [i for i in items if i not in drop]

    copy_root = _copied_fixtures_with_gt_edit(fixtures_root, tmp_path, edit, name="fx_no_engineered")
    report = run_bench(copy_root, out_dir=None)
    assert "cefazolin-reaction" not in report.thread_recall_rate
    assert "falls-risk" not in report.thread_recall_rate
    assert not any("cefazolin-reaction" in v or "falls-risk" in v for v in report.floor_violations)


# --------------------------------------------------------------------------- #
# falls-risk baseline leak -> the "vocabulary gap should elude naive RAG
# entirely" floor fires. Forced via a monkeypatched _baseline_top5 (the real
# engine/ward is untouched) since the real fixture is honestly engineered
# to never trigger this on its own.
# --------------------------------------------------------------------------- #


def test_bench_flags_engineered_thread_recall_drop_under_starved_budget(fixtures_root):
    # A near-zero budget starves every brief down to zero cards, so the
    # engineered threads legitimately drop below their 1.0 recall floor —
    # proving bench.py's own "rate < 1.0" detection fires, not just the
    # (already-covered) "failed to separate" comparison against baseline.
    report = run_bench(fixtures_root, out_dir=None, budget=1)
    for tid in ("cefazolin-reaction", "falls-risk"):
        rate = report.thread_recall_rate[tid]
        assert rate["lamplight"] < 1.0
    joined = " | ".join(report.floor_violations)
    assert "cefazolin-reaction: lamplight rate" in joined
    assert "falls-risk: lamplight rate" in joined
    assert report.ok is False


def test_bench_flags_falls_risk_baseline_leak(fixtures_root, monkeypatch):
    real_baseline_top5 = bench_mod._baseline_top5

    def leaky_baseline_top5(engine, bed, as_of, qvec):
        top = real_baseline_top5(engine, bed, as_of, qvec)
        if bed == 3 and "ep-03-07-2" not in top:
            top = list(top[:4]) + ["ep-03-07-2"]
        return top

    monkeypatch.setattr(bench_mod, "_baseline_top5", leaky_baseline_top5)
    report = run_bench(fixtures_root, out_dir=None)
    rate = report.thread_recall_rate["falls-risk"]
    assert rate["baseline"] > 0.0
    assert any("falls-risk: baseline" in v for v in report.floor_violations)
    assert report.ok is False
