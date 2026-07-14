#!/usr/bin/env python3
"""seed.py — build the Ward 5-Day fixture set from hand-authored source.

    python seed.py --regen          # (re)write fixtures/ward_5day — byte-identical
    python seed.py --check          # verify committed fixtures match the source
    python seed.py --regen --llm    # OPTIONAL: draft prose variants with
                                    # qwen3.7-max for human review (disclosed;
                                    # NEVER used unreviewed, requires
                                    # DASHSCOPE_API_KEY; the committed fixtures
                                    # are the hand-authored ones)

Outputs (all deterministic, pure functions of seed_data/ward.py):
    fixtures/ward_5day/notes/shift_NN/bed_NN.txt      one note per bed/shift
    fixtures/ward_5day/extraction/shift_NN/bed_NN.json committed extraction
        fixture per note: {note_sha256, episodes[...]} — FakeQwen refuses to
        extract if the note hash drifts from its fixture
    fixtures/ward_5day/ground_truth.json               per-shift critical items
        + expiry schedule (drives recall@5 and forgetting precision)

SYNTHETIC DATA ONLY — no real patients, no PHI (see seed_data/ward.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from lamplight_memory.clock import iso, shift_kind, shift_start  # noqa: E402
from seed_data.ward import BEDS, EXPIRY, PATIENTS, THREADS, WARD  # noqa: E402

N_SHIFTS = 15
FIXTURES = REPO / "fixtures" / "ward_5day"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def note_text(bed: int, shift: int) -> str:
    p = PATIENTS[bed]
    header = (
        f"Bed {bed} — {p['name']} ({p['age']}{p['sex']}, {p['dx']}) — "
        f"shift {shift} ({shift_kind(shift)})"
    )
    return f"{header}\n\n{WARD[(bed, shift)]['note']}\n"


def episode_fixture(bed: int, shift: int) -> dict:
    text = note_text(bed, shift)
    episodes = []
    for spec in WARD[(bed, shift)]["episodes"]:
        k = spec["k"]
        ts = iso(shift_start(shift) + timedelta(minutes=90 + 45 * (k - 1)))
        episodes.append(
            {
                "id": f"ep-{bed:02d}-{shift:02d}-{k}",
                "bed": bed,
                "shift": shift,
                "ts": ts,
                "type": spec["type"],
                "text": spec["text"],
                "entities": sorted(set(spec["entities"])),
                "polarity": spec["polarity"],
                "decay_class": spec["decay_class"],
                "resolves": spec["resolves"],
                "why_hint": spec["why_hint"],
            }
        )
    return {"note_sha256": sha256_hex(text), "episodes": episodes}


def ground_truth() -> dict:
    per_shift: dict[str, list[str]] = {}
    for incoming in range(3, N_SHIFTS + 1):
        active = [
            t["id"]
            for t in THREADS
            if t["active_from_shift"] <= incoming
            and (t["resolved_at_shift"] is None or t["resolved_at_shift"] >= incoming)
        ]
        per_shift[str(incoming)] = sorted(active)
    return {
        "disclaimer": (
            "SYNTHETIC ward — hand-authored fixture for benchmarking. "
            "No real patients or PHI."
        ),
        "n_shifts": N_SHIFTS,
        "beds": BEDS,
        "threads": THREADS,
        "expiry": EXPIRY,
        "per_shift": per_shift,
    }


def build() -> dict[str, str]:
    """Return {relative_path: content} for every fixture file."""
    files: dict[str, str] = {}
    for shift in range(1, N_SHIFTS + 1):
        for bed in BEDS:
            files[f"notes/shift_{shift:02d}/bed_{bed:02d}.txt"] = note_text(bed, shift)
            files[f"extraction/shift_{shift:02d}/bed_{bed:02d}.json"] = (
                canonical(episode_fixture(bed, shift)) + "\n"
            )
    files["ground_truth.json"] = canonical(ground_truth()) + "\n"
    return files


def regen() -> int:
    n = 0
    for rel, content in sorted(build().items()):
        path = FIXTURES / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        n += 1
    print(f"wrote {n} fixture files under {FIXTURES}")
    return 0


def check() -> int:
    bad = []
    for rel, content in sorted(build().items()):
        path = FIXTURES / rel
        if not path.exists():
            bad.append(f"MISSING {rel}")
        elif path.read_text(encoding="utf-8") != content:
            bad.append(f"DRIFT   {rel}")
    if bad:
        print("\n".join(bad))
        print(f"{len(bad)} fixture problems — run `python seed.py --regen`")
        return 1
    print("fixtures byte-identical to hand-authored source ✓")
    return 0


def llm_draft() -> int:
    """Disclosed helper: draft alternative prose with qwen3.7-max for human
    review. Writes to fixtures/ward_5day/_llm_drafts/ only — never replaces
    the committed hand-authored notes."""
    import os

    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("--llm requires DASHSCOPE_API_KEY", file=sys.stderr)
        return 2
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    out_dir = FIXTURES / "_llm_drafts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for (bed, shift), entry in sorted(WARD.items()):
        resp = client.chat.completions.create(
            model="qwen3.7-max",  # seed generation only, disclosed (SPEC §6)
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite this synthetic nursing shift note in a natural "
                        "clinical register. Keep every clinical fact EXACTLY; "
                        "change only phrasing. 2-5 sentences."
                    ),
                },
                {"role": "user", "content": entry["note"]},
            ],
            temperature=0.0,
        )
        (out_dir / f"s{shift:02d}_b{bed:02d}.txt").write_text(
            resp.choices[0].message.content or "", encoding="utf-8"
        )
    print(f"drafts in {out_dir} — review by hand; committed fixtures unchanged")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regen", action="store_true", help="write fixtures")
    ap.add_argument("--check", action="store_true", help="verify fixtures match source")
    ap.add_argument("--llm", action="store_true", help="draft prose variants (review only)")
    args = ap.parse_args()
    if args.llm:
        rc = llm_draft()
        if rc:
            return rc
    if args.regen:
        return regen()
    if args.check:
        return check()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
