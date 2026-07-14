#!/usr/bin/env python3
"""render_brief.py — generate the self-contained static brief page.

Reads the committed hero brief (fixtures/.../expected/brief_bed9_shift15.json)
and writes web/brief.html with the JSON embedded inline, so it renders offline
from file:// with no server and no fetch. Regenerate after a replay re-freeze:

    python web/render_brief.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIEF = REPO / "fixtures" / "ward_5day" / "expected" / "brief_bed9_shift15.json"
OUT = REPO / "web" / "brief.html"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lamplight — Bed 9 handover brief</title>
<style>
  :root {
    --ink:#101418; --panel:#161c22; --panel2:#1c242c; --line:#2a343d;
    --gold:#F4B860; --teal:#2DD4BF; --red:#F26D6D; --text:#E6EDF3; --muted:#8AA0B0;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--ink); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
    line-height:1.5; padding:24px; }
  .wrap { max-width:820px; margin:0 auto; }
  .banner { background:rgba(242,109,109,.1); border:1px solid rgba(242,109,109,.35);
    color:#f5b7b7; border-radius:10px; padding:8px 14px; font-size:12.5px; margin-bottom:20px; }
  h1 { font-size:22px; margin:0 0 2px; }
  h1 .lamp { color:var(--gold); }
  .sub { color:var(--muted); font-size:13px; margin-bottom:18px; }
  .meter { display:flex; align-items:center; gap:12px; margin:14px 0 24px; }
  .bar { flex:1; height:10px; background:var(--panel2); border-radius:6px; overflow:hidden;
    border:1px solid var(--line); }
  .bar > span { display:block; height:100%; background:linear-gradient(90deg,var(--teal),var(--gold)); }
  .meter b { font-family:"JetBrains Mono",ui-monospace,monospace; font-size:13px; color:var(--gold); }
  .card { background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--gold);
    border-radius:12px; padding:16px 18px; margin-bottom:14px; }
  .card.crit { border-left-color:var(--red); }
  .card .rank { color:var(--muted); font-family:"JetBrains Mono",monospace; font-size:12px; }
  .card .flag { color:var(--red); font-weight:600; font-size:12px; margin-left:8px; }
  .sbar { margin:6px 0 10px; }
  .why { color:var(--teal); font-size:13.5px; margin-bottom:10px; }
  .why::before { content:"WHY TONIGHT  "; color:var(--muted); font-size:10.5px; letter-spacing:.08em; }
  .cites { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { font-family:"JetBrains Mono",monospace; font-size:11.5px; color:var(--gold);
    background:rgba(244,184,96,.1); border:1px solid rgba(244,184,96,.3);
    padding:2px 8px; border-radius:20px; }
  .decay { color:var(--muted); font-size:12px; margin-top:8px; font-style:italic; }
  .retired { margin-top:26px; }
  .retired h2 { font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }
  .struck { color:var(--muted); text-decoration:line-through; text-decoration-color:var(--red);
    background:var(--panel); border:1px dashed var(--line); border-radius:10px;
    padding:10px 14px; font-size:13.5px; }
  .struck .tag { text-decoration:none; color:var(--teal); font-family:"JetBrains Mono",monospace;
    font-size:11px; margin-left:6px; }
  .foot { color:var(--muted); font-size:12px; margin-top:26px; border-top:1px solid var(--line);
    padding-top:12px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="banner">⚠️ SYNTHETIC DATA ONLY — no real patients, no PHI. Research prototype, not a medical device.</div>
  <h1>🏮 <span class="lamp">Lamplight</span> — Bed <span id="bed"></span> handover</h1>
  <div class="sub" id="sub"></div>
  <div class="meter">
    <span style="color:var(--muted);font-size:12px">BUDGET</span>
    <div class="bar"><span id="fill"></span></div>
    <b id="meter"></b>
  </div>
  <div id="cards"></div>
  <div class="retired" id="retired"></div>
  <div class="foot" id="foot"></div>
</div>
<script>
const BRIEF = __BRIEF_JSON__;
const $ = (id) => document.getElementById(id);
$("bed").textContent = BRIEF.bed;
$("sub").textContent = `Incoming shift ${BRIEF.for_shift} · memory as of close of shift ${BRIEF.as_of_shift} · engine: ${BRIEF.engine}`;
const pct = Math.round(100 * BRIEF.token_count / BRIEF.budget);
$("fill").style.width = pct + "%";
$("meter").textContent = `${BRIEF.token_count} / ${BRIEF.budget} tok`;
$("cards").innerHTML = BRIEF.cards.map(c => `
  <div class="card ${/critical class/.test(c.sbar) || c.needs_confirmation ? 'crit' : ''}">
    <div><span class="rank">#${c.priority}</span>${c.needs_confirmation ? '<span class="flag">CONFIRM?</span>' : ''}</div>
    <div class="sbar">${esc(c.sbar)}</div>
    <div class="why">${esc(c.why_tonight)}</div>
    ${c.decay_note ? `<div class="decay">${esc(c.decay_note)}</div>` : ''}
    <div class="cites">${c.citations.map(id => `<span class="chip">${esc(id)}</span>`).join('')}</div>
  </div>`).join('');
if (BRIEF.retired.length) {
  $("retired").innerHTML = '<h2>Retired — deliberately forgotten</h2>' + BRIEF.retired.map(r =>
    `<div class="struck">${esc(r.label)} <span class="tag">${r.reason} s${r.at_shift} · see ${esc(r.citation)}</span></div>`
  ).join('');
}
$("foot").textContent = `${BRIEF.routine_expired_count} routine items decayed out on schedule · every line above cites a live source episode (validator-enforced).`;
function esc(s){ return String(s).replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m])); }
</script>
</body>
</html>
"""


def main() -> int:
    brief = json.loads(BRIEF.read_text(encoding="utf-8"))
    html = TEMPLATE.replace("__BRIEF_JSON__", json.dumps(brief))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes) from {BRIEF.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
