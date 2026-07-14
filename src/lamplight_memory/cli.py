"""`lamplight` CLI (typer).

    lamplight demo              # one-shot: ingest all 15 shifts + hero brief
    lamplight ingest --shift 4 fixtures/ward_5day/notes/shift_04
    lamplight brief --bed 9 --budget 2000
    lamplight bench
    lamplight verify-chain
    lamplight replay            # zero-key judge path (I5)
    lamplight pin ep-03-07-2
    lamplight feedback --brief-id 1 --card 0 --action confirm

Transport defaults to the offline FakeQwen; pass --transport live with
DASHSCOPE_API_KEY set for Qwen Cloud.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from .bench import run_bench
from .brief import DEFAULT_BUDGET
from .chain import ChainAudit
from .engine import LamplightEngine
from .paths import find_fixtures, repo_root_guess
from .replay import HERO_BED, HERO_BRIEF_SHIFT, build_ward
from .replay import replay as run_replay
from .schemas import Brief
from .transport import get_transport
from .util import canonical_json

app = typer.Typer(
    name="lamplight",
    help="Cross-shift memory engine: ingest, consolidate, decay, brief — with signed ops.",
    no_args_is_help=True,
    add_completion=False,
)

DB_OPT = typer.Option("lamplight.db", "--db", help="SQLite ward database path.")
TRANSPORT_OPT = typer.Option(
    "fake", "--transport", help="'fake' (offline, deterministic) or 'live' (Qwen Cloud)."
)
FIXTURES_OPT = typer.Option(
    None, "--fixtures", help="fixtures/ward_5day path (auto-detected if omitted)."
)


def _engine(db: str, transport: str, fixtures: Path | None, seal: bool = True) -> LamplightEngine:
    fixtures_root = None
    if transport == "fake":
        fixtures_root = find_fixtures(fixtures)
    tr = get_transport(transport, fixtures_root=fixtures_root)
    return LamplightEngine(db, tr, seal=seal)


@app.command()
def ingest(
    notes_dir: Path = typer.Argument(..., help="Directory of bed_*.txt notes for one shift."),
    shift: int = typer.Option(..., "--shift", min=1, help="1-based shift number."),
    db: str = DB_OPT,
    transport: str = TRANSPORT_OPT,
    fixtures: Path | None = FIXTURES_OPT,
):
    """Ingest one shift of notes and run the close-of-shift lifecycle
    (resolutions, decay sweep, nightly consolidation on shifts 3/6/9/12/15)."""
    engine = _engine(db, transport, fixtures)
    try:
        summary = engine.ingest_shift(shift, notes_dir)
    finally:
        engine.close()
    typer.echo(
        f"shift {shift}: {summary['episodes']} episodes ingested; ops "
        + ", ".join(f"{k}={v}" for k, v in sorted(summary["ops"].items()))
    )


@app.command()
def brief(
    bed: int = typer.Option(..., "--bed", help="Bed number."),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", help="Hard token budget."),
    shift: int | None = typer.Option(
        None, "--shift",
        help="Brief FOR this incoming shift (state after shift-1 closed). "
        "Default: after the last ingested shift.",
    ),
    db: str = DB_OPT,
    transport: str = TRANSPORT_OPT,
    fixtures: Path | None = FIXTURES_OPT,
    as_json: bool = typer.Option(False, "--json", help="Print raw BriefCard JSON only."),
):
    """Build the SBAR handover brief for one bed (validated citations, hard budget)."""
    engine = _engine(db, transport, fixtures)
    try:
        as_of = shift - 1 if shift is not None else None
        b = engine.brief(bed, as_of_shift=as_of, budget=budget)
    finally:
        engine.close()
    if as_json:
        typer.echo(canonical_json(b.model_dump()))
        return
    _print_brief(b)


def _print_brief(b: Brief) -> None:
    """Render a brief for the terminal (shared by `brief` and `demo`)."""
    typer.echo(f"— Brief · bed {b.bed} · incoming shift {b.for_shift} "
               f"(memory as of close of s{b.as_of_shift}) —")
    typer.echo(f"budget: {b.token_count}/{b.budget} tokens · engine: {b.engine}")
    for card in b.cards:
        flag = "  [CONFIRM?]" if card.needs_confirmation else ""
        typer.echo(f"\n#{card.priority}{flag} {card.sbar}")
        typer.echo(f"   why tonight: {card.why_tonight}")
        if card.decay_note:
            typer.echo(f"   decay note: {card.decay_note}")
        typer.echo(f"   citations: {' '.join('[' + c + ']' for c in card.citations)}")
    if b.retired:
        typer.echo("\n— retired (deliberately forgotten) —")
        for r in b.retired:
            typer.echo(f"  ~~{r.label}~~ ({r.reason} s{r.at_shift}; see [{r.citation}])")
    if b.routine_expired_count:
        typer.echo(f"  + {b.routine_expired_count} routine items decayed out on schedule")
    if b.left_out:
        typer.echo("\n— didn't make the cut —")
        for lo in b.left_out[:5]:
            typer.echo(f"  [{lo.reason}] {lo.id} (value {lo.value}, {lo.tokens} tok)")


@app.command()
def demo(
    bed: int = typer.Option(HERO_BED, "--bed", help="Bed number (default: the hero bed 9)."),
    shift: int = typer.Option(
        HERO_BRIEF_SHIFT, "--shift",
        help="Brief FOR this incoming shift (default: 15, the hero brief).",
    ),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", help="Hard token budget."),
    db: str = typer.Option(
        "lamplight-demo.db", "--db",
        help="Ward DB to (re)build for the demo — rebuilt fresh each run.",
    ),
    fixtures: Path | None = FIXTURES_OPT,
):
    """One-shot judge path: ingest all 15 fixture shifts into a fresh ward DB,
    then print the hero brief — cited, budgeted, with the resolved IV item
    visibly forgotten. This is the copy-paste "money shot"; it needs no prior
    `ingest` and leaves a real `--db lamplight-demo.db` you can `verify-chain`."""
    fixtures_root = find_fixtures(fixtures)
    db_path = Path(db)
    if db_path.exists():
        db_path.unlink()  # rebuild fresh — no double-ingest into a stale ward
    engine = LamplightEngine(db_path, get_transport("fake", fixtures_root=fixtures_root), seal=True)
    try:
        build_ward(engine, fixtures_root)  # ingests all 15 shifts + nightly lifecycle
        b = engine.brief(bed, as_of_shift=shift - 1, budget=budget)
    finally:
        engine.close()
    typer.echo(f"ingested 15 shifts into a fresh ward ({db_path}) — signed op chain built.\n")
    _print_brief(b)
    typer.echo(f"\n(audit it: lamplight verify-chain --db {db_path})")


@app.command()
def bench(
    fixtures: Path | None = FIXTURES_OPT,
    out: Path | None = typer.Option(
        None, "--out", help="Output dir for RESULTS.md + summary.json "
        "(default: <repo>/bench_results)."
    ),
    transport: str = TRANSPORT_OPT,
):
    """Recall@5 curves vs naive RAG + forgetting precision + $/patient-day."""
    fixtures_root = find_fixtures(fixtures)
    out_dir = out or (repo_root_guess() / "bench_results")
    tr = None
    if transport == "live":
        tr = get_transport("live")
    report = run_bench(fixtures_root, out_dir=out_dir, transport=tr)
    from .bench import render_markdown

    typer.echo(render_markdown(report))
    typer.echo(f"(written to {out_dir}/RESULTS.md)")
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("verify-chain")
def verify_chain(db: str = DB_OPT):
    """Verify the Ed25519 hash-chained op ledger (I4)."""
    audit = ChainAudit(db)
    try:
        report = audit.verify()
    finally:
        audit.close()
    typer.echo(json.dumps(report.as_dict(), indent=2))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def replay(
    fixtures: Path | None = FIXTURES_OPT,
    write_expected: bool = typer.Option(
        False, "--write-expected",
        help="Freeze the current output as the committed expected brief (maintainer use).",
    ),
):
    """Zero-key judge path: rebuild the ward from fixtures, regenerate the
    Bed-9 shift-15 brief, byte-compare to the committed expected JSON, and
    verify the op chain (I4 + I5)."""
    fixtures_root = find_fixtures(fixtures)
    result = run_replay(fixtures_root, write_expected=write_expected)
    typer.echo(f"chain: {'OK' if result.chain.ok else 'FAIL'} "
               f"({result.chain.length} signed ops, pubkey {result.chain.pubkey[:16]}…)")
    typer.echo(f"brief: {'byte-identical' if result.byte_identical else 'MISMATCH'} "
               f"vs {result.expected_path.name}")
    typer.echo(result.detail)
    if not result.ok:
        raise typer.Exit(code=1)
    typer.echo("REPLAY PASS")


@app.command()
def pin(
    item_id: str = typer.Argument(..., help="Episode or memory id to pin."),
    db: str = DB_OPT,
):
    """Pin an item: exempt from decay, strength held at 1.0 (signed op)."""
    from .transport.fake import FakeQwen

    engine = LamplightEngine(db, FakeQwen(extraction_map={}), seal=True)
    try:
        ok = engine.pin(item_id)
    finally:
        engine.close()
    if not ok:
        typer.echo(f"could not pin {item_id} (not found or not active)")
        raise typer.Exit(code=1)
    typer.echo(f"pinned {item_id}")


@app.command()
def feedback(
    brief_id: int = typer.Option(..., "--brief-id"),
    card: int = typer.Option(..., "--card", help="0-based card index."),
    action: str = typer.Option(..., "--action", help="confirm | correct | dismiss"),
    db: str = DB_OPT,
):
    """Nurse feedback on a brief card: confirm strengthens (s0 +0.25),
    correct halves strength, dismiss expires. All signed ops."""
    from .transport.fake import FakeQwen

    engine = LamplightEngine(db, FakeQwen(extraction_map={}), seal=True)
    try:
        result = engine.feedback(brief_id, card, action)
    finally:
        engine.close()
    typer.echo(json.dumps(result))


def main() -> None:  # console-script entry
    app()


if __name__ == "__main__":  # pragma: no cover — pure entry-point boilerplate;
    # `main()` itself is exercised directly by tests/test_cli.py.
    sys.exit(main())
