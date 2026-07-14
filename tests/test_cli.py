"""`lamplight` CLI smoke tests (typer CliRunner, offline fake transport)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from lamplight_memory.cli import app
from lamplight_memory.engine import LamplightEngine
from lamplight_memory.replay import build_ward
from lamplight_memory.transport.fake import FakeQwen

runner = CliRunner()


@pytest.fixture(scope="module")
def ward_db(fixtures_root, tmp_path_factory):
    db = tmp_path_factory.mktemp("cli") / "ward.db"
    engine = LamplightEngine(db, FakeQwen(fixtures_root=fixtures_root), seal=True)
    build_ward(engine, fixtures_root)
    engine.close()
    return str(db)


def test_no_args_shows_help():
    # typer's no_args_is_help prints usage and exits with code 2
    result = runner.invoke(app, [])
    assert result.exit_code in (0, 2)
    assert "ingest" in result.stdout and "brief" in result.stdout


def test_replay_command_passes():
    result = runner.invoke(app, ["replay"])
    assert result.exit_code == 0, result.stdout
    assert "REPLAY PASS" in result.stdout
    assert "byte-identical" in result.stdout


def test_verify_chain_command(ward_db):
    result = runner.invoke(app, ["verify-chain", "--db", ward_db])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["length"] > 100


def test_brief_command_human(ward_db):
    result = runner.invoke(app, ["brief", "--bed", "9", "--shift", "15", "--db", ward_db])
    assert result.exit_code == 0, result.stdout
    assert "cefazolin" in result.stdout.lower()
    assert "budget:" in result.stdout
    assert "retired" in result.stdout.lower()


def test_brief_command_json(ward_db):
    result = runner.invoke(
        app, ["brief", "--bed", "9", "--shift", "15", "--db", ward_db, "--json"]
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["bed"] == 9
    assert data["token_count"] <= 2000


def test_brief_budget_flag(ward_db):
    result = runner.invoke(
        app, ["brief", "--bed", "9", "--shift", "15", "--db", ward_db, "--budget", "150", "--json"]
    )
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["token_count"] <= 150


def test_pin_then_verify(ward_db):
    result = runner.invoke(app, ["pin", "ep-03-01-2", "--db", ward_db])
    assert result.exit_code == 0, result.stdout
    assert "pinned" in result.stdout
    # chain still verifies after the signed pin op
    v = runner.invoke(app, ["verify-chain", "--db", ward_db])
    assert json.loads(v.stdout)["ok"] is True


# --------------------------------------------------------------------------- #
# ingest command
# --------------------------------------------------------------------------- #


def test_ingest_command(fixtures_root, tmp_path):
    db = str(tmp_path / "ingest_cli.db")
    notes_dir = fixtures_root / "notes" / "shift_01"
    result = runner.invoke(app, ["ingest", str(notes_dir), "--shift", "1", "--db", db])
    assert result.exit_code == 0, result.stdout
    assert "shift 1:" in result.stdout
    assert "episodes ingested" in result.stdout
    assert "write=" in result.stdout


# --------------------------------------------------------------------------- #
# demo command: one-shot ingest-all-15 + hero brief (the money shot)
# --------------------------------------------------------------------------- #


def test_demo_command_builds_ward_and_briefs(fixtures_root, tmp_path):
    db = str(tmp_path / "demo_cli.db")
    result = runner.invoke(app, ["demo", "--fixtures", str(fixtures_root), "--db", db])
    assert result.exit_code == 0, result.stdout
    # no prior ingest needed: it builds the whole ward itself
    assert "ingested 15 shifts" in result.stdout
    # the money shot: cefazolin card #1 + the deliberately-forgotten IV item
    assert "cefazolin" in result.stdout.lower()
    assert "retired" in result.stdout.lower()
    assert "budget:" in result.stdout
    # non-empty brief (the bug this command fixes was a 0-token empty brief)
    assert "budget: 0/" not in result.stdout
    # leaves a real, auditable db
    v = runner.invoke(app, ["verify-chain", "--db", db])
    assert json.loads(v.stdout)["ok"] is True


def test_demo_command_rebuilds_existing_db(fixtures_root, tmp_path):
    # a stale db at the target path is rebuilt fresh, not double-ingested
    db = tmp_path / "demo_rebuild.db"
    db.write_bytes(b"not a real database")
    result = runner.invoke(app, ["demo", "--fixtures", str(fixtures_root), "--db", str(db)])
    assert result.exit_code == 0, result.stdout
    assert "cefazolin" in result.stdout.lower()


# --------------------------------------------------------------------------- #
# brief command: decay-note line + left_out (budget scarcity) branches
# --------------------------------------------------------------------------- #


def test_brief_command_prints_decay_note(ward_db):
    # bed 3 at incoming shift 15 has a card whose related item retired
    # (see tests/test_brief.py's direct check of this same fixture state)
    result = runner.invoke(app, ["brief", "--bed", "3", "--shift", "15", "--db", ward_db])
    assert result.exit_code == 0, result.stdout
    assert "decay note:" in result.stdout


def test_brief_command_prints_left_out_under_tiny_budget(ward_db):
    result = runner.invoke(
        app, ["brief", "--bed", "9", "--shift", "15", "--db", ward_db, "--budget", "120"]
    )
    assert result.exit_code == 0, result.stdout
    assert "didn't make the cut" in result.stdout


# --------------------------------------------------------------------------- #
# bench command
# --------------------------------------------------------------------------- #


def test_bench_command_real_run_writes_out_dir(tmp_path, fixtures_root):
    out_dir = tmp_path / "bench_cli_out"
    result = runner.invoke(
        app, ["bench", "--fixtures", str(fixtures_root), "--out", str(out_dir)]
    )
    assert result.exit_code == 0, result.stdout
    assert "Lamplight memory bench" in result.stdout
    assert f"written to {out_dir}/RESULTS.md" in result.stdout
    assert (out_dir / "RESULTS.md").exists()
    assert (out_dir / "summary.json").exists()


def test_bench_command_live_transport_dispatch(monkeypatch, fixtures_root, tmp_path):
    # proves the --transport live wiring (cli.get_transport("live")) without
    # a real network call: substitute a deterministic offline transport that
    # merely reports itself as "live", so run_bench's own logic still runs
    # for real end-to-end.
    from lamplight_memory import cli as cli_mod
    from lamplight_memory.transport.fake import FakeQwen

    def fake_get_transport(name, fixtures_root=None, extraction_map=None):
        assert name == "live"
        tr = FakeQwen(fixtures_root=find_root)
        tr.name = "live"
        return tr

    find_root = fixtures_root
    monkeypatch.setattr(cli_mod, "get_transport", fake_get_transport)
    out_dir = tmp_path / "bench_cli_live_out"
    result = runner.invoke(
        app,
        ["bench", "--fixtures", str(fixtures_root), "--transport", "live", "--out", str(out_dir)],
    )
    assert result.exit_code == 0, result.stdout
    assert (out_dir / "summary.json").exists()
    assert json.loads((out_dir / "summary.json").read_text())["engine"] == "live"


def test_bench_command_exits_nonzero_on_floor_violation(monkeypatch, tmp_path):
    from lamplight_memory import cli as cli_mod
    from lamplight_memory.bench import BenchReport

    def fake_run_bench(fixtures_root, out_dir=None, transport=None):
        report = BenchReport(floor_violations=["synthetic failure for cli exit test"])
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
        return report

    monkeypatch.setattr(cli_mod, "run_bench", fake_run_bench)
    result = runner.invoke(app, ["bench", "--out", str(tmp_path / "bench_cli_fail")])
    assert result.exit_code == 1
    assert "synthetic failure for cli exit test" in result.stdout


# --------------------------------------------------------------------------- #
# verify-chain / replay: nonzero exit on failure
# --------------------------------------------------------------------------- #


def test_verify_chain_command_nonzero_exit_on_broken_chain(ward_db):
    import sqlite3

    con = sqlite3.connect(ward_db)
    con.execute("UPDATE op_chain SET sig=? WHERE seq=1", ("00" * 64,))
    con.commit()
    con.close()
    result = runner.invoke(app, ["verify-chain", "--db", ward_db])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_replay_command_nonzero_exit_on_failure(monkeypatch):
    from pathlib import Path

    from lamplight_memory import cli as cli_mod
    from lamplight_memory.chain import ChainReport
    from lamplight_memory.replay import ReplayResult

    def fake_replay(fixtures_root, write_expected=False):
        chain = ChainReport(ok=True, length=5, pubkey="ab" * 32)
        return ReplayResult(
            ok=False, byte_identical=False, chain=chain,
            brief_bytes=b"{}", expected_path=Path("expected.json"),
            detail="brief DIFFERS from committed expected; ",
        )

    monkeypatch.setattr(cli_mod, "run_replay", fake_replay)
    result = runner.invoke(app, ["replay"])
    assert result.exit_code == 1
    assert "MISMATCH" in result.stdout
    assert "REPLAY PASS" not in result.stdout


# --------------------------------------------------------------------------- #
# pin: not-found / not-active exit
# --------------------------------------------------------------------------- #


def test_pin_command_nonexistent_item_nonzero_exit(ward_db):
    result = runner.invoke(app, ["pin", "ep-does-not-exist", "--db", ward_db])
    assert result.exit_code == 1
    assert "could not pin" in result.stdout


# --------------------------------------------------------------------------- #
# feedback command
# --------------------------------------------------------------------------- #


def test_feedback_command(ward_db):
    import sqlite3

    result = runner.invoke(
        app, ["brief", "--bed", "9", "--shift", "15", "--db", ward_db, "--json"]
    )
    assert result.exit_code == 0, result.stdout
    con = sqlite3.connect(ward_db)
    brief_id = con.execute("SELECT MAX(id) FROM briefs").fetchone()[0]
    con.close()
    assert brief_id is not None

    result2 = runner.invoke(
        app,
        ["feedback", "--brief-id", str(brief_id), "--card", "0", "--action", "confirm", "--db", ward_db],
    )
    assert result2.exit_code == 0, result2.stdout
    payload = json.loads(result2.stdout)
    assert payload["action"] == "confirm"


# --------------------------------------------------------------------------- #
# console-script entry point
# --------------------------------------------------------------------------- #


def test_main_entrypoint_invokes_app(monkeypatch):
    import sys

    from lamplight_memory import cli as cli_mod

    monkeypatch.setattr(sys, "argv", ["lamplight", "verify-chain", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli_mod.main()
    assert exc.value.code == 0
