"""Ward 5-Day — hand-authored synthetic seed data (SEED_DATA.md).

*** 100% SYNTHETIC. No real patients, no PHI. Names, vitals and events are
*** invented for a benchmark fixture. This is a research prototype, not a
*** medical device.

Authoring notes
---------------
- Every note AND its structured extraction were written by hand, together,
  so the extraction fixtures are frozen and committed per note (no LLM is
  required to rebuild the ward; `seed.py --regen` is byte-identical).
  An optional `seed.py --llm` path exists to *draft* prose variants with
  qwen3.7-max (disclosed in SPEC §6); its output is never used unreviewed.
- Planted, ground-truth-labeled threads (SEED_DATA.md):
    1. cefazolin-rash chain, bed 9 (shifts 4 -> 6 -> 12) with a deliberate
       vocabulary gap: "erythema", "red patches", "rash" — three phrasings,
       one thread. Naive cosine retrieval cannot bridge it; entity
       consolidation can.
    2. swallowed falls-risk, bed 3 (shift 7): one low-salience clause
       ("unsteady ... to the bathroom") buried mid-note.
    3. resolved red herring, bed 9: IV-site concern (s1) resolved s2 —
       must NEVER surface after s2 (forgetting precision).
    4. contradiction pair, bed 5: "slept well" (day, s10) vs "up 4x
       overnight" (night, s12).
    5. noise floor: ~85% routine episodes (vitals, meals, ambulation,
       sleep, hygiene) that share vocabulary with the handover query.
- 15 shifts = 5 days x (day 07-15 / evening 15-23 / night 23-07).

Episode dict fields: k (1-based order in note), type, text, entities,
polarity, decay_class, resolves, why_hint — id/ts/bed/shift are derived
deterministically by seed.py.
"""

from __future__ import annotations

BEDS = [3, 5, 7, 9, 11, 12]

PATIENTS = {
    3: {"name": "Alma Reyes", "age": 78, "sex": "F",
        "dx": "right total hip replacement, atrial fibrillation on warfarin"},
    5: {"name": "Harold Kim", "age": 66, "sex": "M",
        "dx": "community-acquired pneumonia"},
    7: {"name": "Dev Okafor", "age": 34, "sex": "M",
        "dx": "post-op laparoscopic appendectomy, seizure history"},
    9: {"name": "June Park", "age": 52, "sex": "F",
        "dx": "left lower-leg cellulitis"},
    11: {"name": "Rose Ngata", "age": 81, "sex": "F",
         "dx": "congestive heart failure exacerbation"},
    12: {"name": "Sam Alvarez", "age": 59, "sex": "M",
         "dx": "COPD exacerbation"},
}


def _ep(k, text, entities, decay_class="routine", type="observation",
        polarity="neutral", resolves=None, why_hint=None):
    return {
        "k": k, "type": type, "text": text, "entities": entities,
        "polarity": polarity, "decay_class": decay_class,
        "resolves": resolves, "why_hint": why_hint,
    }


WARD: dict[tuple[int, int], dict] = {}

# ===================================================================== #
# BED 3 — Alma Reyes, 78F. Hip replacement POD2 at s1; AF on warfarin.
# Planted: warfarin bleeding-risk (critical, s1 + s10), swallowed
# falls-risk mention (critical, s7).
# ===================================================================== #

WARD[(3, 1)] = {
    "note": (
        "Received from surgical stepdown, post-op day 2 right total hip replacement. "
        "Hip dressing dry and intact, pain 4/10 settling with paracetamol. "
        "She is on warfarin for atrial fibrillation - bleeding risk, INR pending from the morning draw. "
        "Tolerating a light diet, using the call bell appropriately."
    ),
    "episodes": [
        _ep(1, "Post-op day 2 right hip replacement: dressing dry and intact, pain 4/10 settling with paracetamol, tolerating light diet.",
            ["wound", "pain"], "routine"),
        _ep(2, "On warfarin for atrial fibrillation - bleeding risk; INR pending from morning draw.",
            ["warfarin"], "critical", type="observation",
            why_hint="anticoagulated - check INR result and bleeding precautions before any invasive care"),
    ],
}
WARD[(3, 2)] = {
    "note": (
        "Evening after first physio session; pain rose to 5/10, settled to 3/10 after oxycodone at 1800. "
        "Daughter visited and helped with supper, ate about half. No calf tenderness, pedal pulses present."
    ),
    "episodes": [
        _ep(1, "Pain 5/10 after physio, settled to 3/10 with oxycodone 1800; ate half of supper; no calf tenderness.",
            ["pain", "meals"], "routine"),
    ],
}
WARD[(3, 3)] = {
    "note": (
        "Night: slept in two long stretches, repositioned at 0200 with assistance. "
        "Voided x1, no dizziness reported while up. Vitals stable, afebrile."
    ),
    "episodes": [
        _ep(1, "Slept in two stretches, repositioned 0200, voided x1, vitals stable and afebrile.",
            ["sleep", "vitals"], "routine"),
    ],
}
WARD[(3, 4)] = {
    "note": (
        "Physio walked her 20 metres with the wheeled frame, good tolerance, mild hip pain 3/10 afterwards. "
        "Dressing changed - wound edges clean, no ooze. Compression stockings on."
    ),
    "episodes": [
        _ep(1, "Walked 20 m with wheeled frame, pain 3/10 after; dressing changed, wound clean, compression stockings on.",
            ["mobility", "wound", "pain"], "routine"),
    ],
}
WARD[(3, 5)] = {
    "note": (
        "Comfortable evening, pain 3/10 at rest. Ate three-quarters of dinner, drinking well. "
        "Practised bed-to-chair transfer with one assist, steady with the frame in the room."
    ),
    "episodes": [
        _ep(1, "Pain 3/10 at rest, ate 75% of dinner, bed-to-chair transfer with one assist.",
            ["pain", "meals", "mobility"], "routine"),
    ],
}
WARD[(3, 6)] = {
    "note": (
        "Uneventful night. Slept after 0030, woke once for analgesia, settled again. "
        "Voided x2 with the frame and standby assist. Morning obs within normal limits."
    ),
    "episodes": [
        _ep(1, "Uneventful night: slept after 0030, one dose of analgesia, voided x2 with standby assist, obs normal.",
            ["sleep", "vitals"], "routine"),
    ],
}
WARD[(3, 7)] = {
    "note": (
        "Busy day shift. Physio progressed her to a single stick for short distances in the room; hip pain 3/10. "
        "She was unsteady on her feet going to the bathroom mid-morning and caught herself on the rail - steadied by the aide, no injury, said she 'just got ahead of herself'. "
        "Dressing dry. Ate well at lunch, family brought photos from home."
    ),
    "episodes": [
        _ep(1, "Physio progressed to single stick for short distances; pain 3/10; dressing dry; ate well at lunch.",
            ["mobility", "pain", "meals"], "routine"),
        _ep(2, "Unsteady on her feet going to the bathroom mid-morning, caught herself on the rail; steadied by aide, no injury.",
            ["falls_risk"], "critical",
            why_hint="near-miss on foot - supervise all transfers and toileting until formally assessed"),
    ],
}
WARD[(3, 8)] = {
    "note": (
        "Quiet evening, pain controlled 2/10. Sat out in the chair for supper, ate most of it. "
        "Niece visited. Requested sleeping tablet for later, offered warm drink first."
    ),
    "episodes": [
        _ep(1, "Pain 2/10, sat out in chair for supper and ate most of it; requested sleeping tablet, offered warm drink.",
            ["pain", "meals", "sleep"], "routine"),
    ],
}
WARD[(3, 9)] = {
    "note": (
        "Night: slept in stretches, up once to the bathroom with the aide standing by as planned, steady with the frame this time. "
        "No pain overnight. Morning bloods taken including INR."
    ),
    "episodes": [
        _ep(1, "Slept in stretches, up once to bathroom with aide standing by, steady with frame; morning bloods incl. INR taken.",
            ["sleep", "mobility"], "routine"),
    ],
}
WARD[(3, 10)] = {
    "note": (
        "INR back at 2.4 - therapeutic; warfarin continued at current dose per team, bleeding precautions remain (soft toothbrush, watch for bruising, pressure after venepuncture). "
        "Physio session went well, walked the corridor with the stick. Pain 2/10."
    ),
    "episodes": [
        _ep(1, "INR 2.4 therapeutic; warfarin continued at current dose; bleeding precautions remain in place.",
            ["warfarin"], "critical",
            why_hint="on warfarin - maintain bleeding precautions and flag any bruising or dark stools"),
        _ep(2, "Walked corridor with stick at physio; pain 2/10.",
            ["mobility", "pain"], "routine"),
    ],
}
WARD[(3, 11)] = {
    "note": (
        "Comfortable evening. Dressing dry, wound review booked for tomorrow. "
        "Ate a full dinner, watched television with her daughter. Pain 2/10 at rest."
    ),
    "episodes": [
        _ep(1, "Dressing dry, wound review booked tomorrow; ate full dinner; pain 2/10 at rest.",
            ["wound", "meals", "pain"], "routine"),
    ],
}
WARD[(3, 12)] = {
    "note": (
        "Slept well overall, woke at 0400 for the bathroom, waited for the aide as asked and was steady. "
        "No new pain. Obs stable through the night."
    ),
    "episodes": [
        _ep(1, "Slept well, woke 0400 for bathroom and waited for aide, steady; no new pain; obs stable.",
            ["sleep", "mobility", "vitals"], "routine"),
    ],
}
WARD[(3, 13)] = {
    "note": (
        "Wound reviewed by the team - healing well, sutures to stay another week. "
        "Physio practised three stairs with the stick, managed with supervision, pain 3/10 after. "
        "Discharge conversation started with family."
    ),
    "episodes": [
        _ep(1, "Wound healing well, sutures stay another week; practised three stairs with supervision, pain 3/10 after; discharge conversation started.",
            ["wound", "mobility", "pain"], "routine"),
    ],
}
WARD[(3, 14)] = {
    "note": (
        "Evening settled. Occupational therapy dropped equipment recommendations for home. "
        "Ate well, pain 2/10. Daughter will collect washing tomorrow."
    ),
    "episodes": [
        _ep(1, "OT left home-equipment recommendations; ate well; pain 2/10.",
            ["meals", "pain"], "routine"),
    ],
}
WARD[(3, 15)] = {
    "note": (
        "Comfortable night, slept from 2330 with one waking. Up once with standby assist, no issues. "
        "Morning obs stable, afebrile, pain 2/10."
    ),
    "episodes": [
        _ep(1, "Comfortable night, one waking, up once with standby assist; obs stable, afebrile, pain 2/10.",
            ["sleep", "vitals", "pain"], "routine"),
    ],
}

# ===================================================================== #
# BED 5 — Harold Kim, 66M. Community-acquired pneumonia.
# Planted: penicillin allergy (critical, s1); sleep contradiction
# (pos s10 day vs neg s12 night).
# ===================================================================== #

WARD[(5, 1)] = {
    "note": (
        "Admitted overnight with right-sided community-acquired pneumonia, on IV levofloxacin. "
        "Allergy documented: penicillin - prior reaction hives and lip swelling in 2019; flagged on the chart and on his armband. "
        "O2 at 2 L nasal prongs, sats 92-94%, crackles right base, productive cough. Temp 37.9."
    ),
    "episodes": [
        _ep(1, "Admitted with right-sided pneumonia on IV levofloxacin; O2 2 L, sats 92-94%, crackles right base, temp 37.9, productive cough.",
            ["oxygen", "vitals", "cough"], "routine"),
        _ep(2, "Allergy documented: penicillin - prior reaction hives and lip swelling (2019); flagged on chart and armband.",
            ["penicillin_allergy"], "critical",
            why_hint="screen every new antibiotic order against the penicillin allergy"),
    ],
}
WARD[(5, 2)] = {
    "note": (
        "Evening temp spiked 38.1, paracetamol given with good effect. Sats holding 93% on 2 L. "
        "Coughing with thick sputum, using the spirometer with coaching. Appetite poor, took soup only."
    ),
    "episodes": [
        _ep(1, "Temp 38.1 settled with paracetamol; sats 93% on 2 L; thick sputum, spirometer with coaching; ate soup only.",
            ["vitals", "oxygen", "cough", "meals"], "routine"),
    ],
}
WARD[(5, 3)] = {
    "note": (
        "Coughing spells through the night, worst around 0100, settled with positioning and a warm drink. "
        "Sats dipped to 91% during one spell, recovered to 93% on 2 L. Dozed between episodes."
    ),
    "episodes": [
        _ep(1, "Coughing spells overnight, worst 0100; sats dipped 91% then recovered to 93% on 2 L; dozed between episodes.",
            ["cough", "oxygen"], "routine"),
    ],
}
WARD[(5, 4)] = {
    "note": (
        "Repeat chest film this morning shows early improvement. O2 weaned to 1 L, sats 94%. "
        "Breathing easier on exertion, walked to the door and back. Temp 37.4."
    ),
    "episodes": [
        _ep(1, "Repeat chest film improving; O2 weaned to 1 L with sats 94%; breathing easier, walked to door and back; temp 37.4.",
            ["oxygen", "breathing", "mobility", "vitals"], "routine"),
    ],
}
WARD[(5, 5)] = {
    "note": (
        "Appetite still poor - half a sandwich at dinner; encouraged fluids, drinking reasonably. "
        "Less febrile, 37.2 this evening. Cough looser, less frequent."
    ),
    "episodes": [
        _ep(1, "Ate half a sandwich, drinking reasonably; temp 37.2; cough looser and less frequent.",
            ["meals", "vitals", "cough"], "routine"),
    ],
}
WARD[(5, 6)] = {
    "note": (
        "Slept with the head of bed elevated, sats steady at 94% on 1 L overnight. "
        "One coughing episode at 0300, short-lived. Comfortable at morning rounds."
    ),
    "episodes": [
        _ep(1, "Slept with HOB elevated; sats 94% on 1 L overnight; one short coughing episode 0300.",
            ["oxygen", "cough"], "routine"),
    ],
}
WARD[(5, 7)] = {
    "note": (
        "Walked the corridor twice with a rest between laps, mild breathlessness on exertion only. "
        "Sats 94% on 1 L, considering weaning off tomorrow. Ate most of lunch, mood brighter."
    ),
    "episodes": [
        _ep(1, "Walked corridor x2 with mild exertional breathlessness; sats 94% on 1 L; ate most of lunch; mood brighter.",
            ["mobility", "breathing", "oxygen", "meals"], "routine"),
    ],
}
WARD[(5, 8)] = {
    "note": (
        "Afebrile 24 hours now. Evening sats 94-95% on 1 L. Productive cough persists but easier. "
        "Wife visited with home cooking, ate well for the first time."
    ),
    "episodes": [
        _ep(1, "Afebrile 24 h; sats 94-95% on 1 L; cough easier; ate well (home cooking).",
            ["vitals", "oxygen", "cough", "meals"], "routine"),
    ],
}
WARD[(5, 9)] = {
    "note": (
        "Minimal cough overnight, slept with one waking for observations. "
        "Sats held 94% on 1 L; trial off oxygen planned for the morning."
    ),
    "episodes": [
        _ep(1, "Minimal cough overnight, one waking for obs; sats 94% on 1 L; trial off O2 planned in the morning.",
            ["cough", "oxygen"], "routine"),
    ],
}
WARD[(5, 10)] = {
    "note": (
        "Oxygen off since 0900, sats 95% on room air including after walking. "
        "He reports he slept well overnight and feels rested today. "
        "Ate a full lunch. Physio happy with progress."
    ),
    "episodes": [
        _ep(1, "O2 off since 0900; sats 95% room air incl. after walking; ate full lunch; physio happy.",
            ["oxygen", "mobility", "meals"], "routine"),
        _ep(2, "Reports he slept well overnight and feels rested today.",
            ["sleep"], "routine", polarity="pos"),
    ],
}
WARD[(5, 11)] = {
    "note": (
        "Comfortable evening on room air, sats 95%. Family visited, played cards in the day room. "
        "Ate most of dinner. Cough now occasional and dry-ish."
    ),
    "episodes": [
        _ep(1, "Room air, sats 95%; family visit, cards in day room; ate most of dinner; occasional cough.",
            ["oxygen", "meals", "cough"], "routine"),
    ],
}
WARD[(5, 12)] = {
    "note": (
        "Rough night in contrast to the day report: up 4 times overnight, dozing in 10-minute stretches between coughing fits, appears exhausted this morning. "
        "Sats dipped to 92% while asleep, recovered to 94% on repositioning; remained on room air."
    ),
    "episodes": [
        _ep(1, "Up 4 times overnight, dozing in 10-minute stretches between coughing fits; appears exhausted this morning.",
            ["sleep"], "routine", polarity="neg"),
        _ep(2, "Sats dipped 92% while asleep, recovered 94% on repositioning; remained on room air.",
            ["oxygen"], "routine"),
    ],
}
WARD[(5, 13)] = {
    "note": (
        "Physio assessed for deconditioning - mild, home exercise plan provided. "
        "Sats 95% room air. Team discussing switch to oral antibiotics tomorrow. Ate well."
    ),
    "episodes": [
        _ep(1, "Physio: mild deconditioning, home exercise plan; sats 95% RA; oral antibiotic switch discussed; ate well.",
            ["mobility", "oxygen", "antibiotics", "meals"], "routine"),
    ],
}
WARD[(5, 14)] = {
    "note": (
        "Switched to oral doxycycline this evening - order screened against his penicillin allergy, no cross-reactivity concern. "
        "Observations stable, sats 95%. Looking forward to discharge planning."
    ),
    "episodes": [
        _ep(1, "Switched to oral doxycycline, screened against penicillin allergy; obs stable, sats 95%.",
            ["antibiotics", "vitals"], "routine"),
    ],
}
WARD[(5, 15)] = {
    "note": (
        "Settled night, coughed twice, self-settled. Sats 94-95% on room air asleep. "
        "Morning obs stable; discharge review today."
    ),
    "episodes": [
        _ep(1, "Settled night, two self-settling coughs; sats 94-95% RA asleep; obs stable; discharge review today.",
            ["cough", "oxygen", "vitals"], "routine"),
    ],
}

# ===================================================================== #
# BED 7 — Dev Okafor, 34M. Appendectomy POD1; seizure history.
# Planted: seizure precautions (critical, s1). Otherwise routine arc.
# ===================================================================== #

WARD[(7, 1)] = {
    "note": (
        "Post-op day 1 laparoscopic appendectomy, three port sites clean and dry. Pain 3/10 with regular analgesia. "
        "Seizure history - on levetiracetam twice daily; seizure precautions in place: padded rails, suction at bedside, last seizure four months ago. "
        "Tolerating clear fluids."
    ),
    "episodes": [
        _ep(1, "POD1 lap appendectomy: port sites clean and dry, pain 3/10 with regular analgesia, tolerating clear fluids.",
            ["wound", "pain", "meals"], "routine"),
        _ep(2, "Seizure history on levetiracetam BD; seizure precautions in place (padded rails, suction at bedside); last seizure four months ago.",
            ["seizure_precautions"], "critical",
            why_hint="do not miss levetiracetam doses (0800/2000); keep precautions set up"),
    ],
}
WARD[(7, 2)] = {
    "note": (
        "Evening: advanced to free fluids, tolerated well. Pain 3/10, mobilising to the bathroom independently and steady. "
        "Levetiracetam given at 2000 as charted."
    ),
    "episodes": [
        _ep(1, "Advanced to free fluids; pain 3/10; mobilising to bathroom independently; levetiracetam given 2000.",
            ["meals", "pain", "mobility"], "routine"),
    ],
}
WARD[(7, 3)] = {
    "note": (
        "Slept most of the night, woke once for water. No nausea. Port sites unremarkable at morning check."
    ),
    "episodes": [
        _ep(1, "Slept most of night, woke once for water; no nausea; port sites unremarkable.",
            ["sleep", "wound"], "routine"),
    ],
}
WARD[(7, 4)] = {
    "note": (
        "Light diet started and tolerated. Walked the ward corridor twice, pain 2/10 on movement. "
        "Bowels not yet open, encouraged mobility and fluids."
    ),
    "episodes": [
        _ep(1, "Light diet tolerated; walked corridor x2; pain 2/10 on movement; bowels not yet open.",
            ["meals", "mobility", "pain"], "routine"),
    ],
}
WARD[(7, 5)] = {
    "note": (
        "Low-grade temp 37.8 at 1700, settled to 37.2 by 2100 after paracetamol; wounds reviewed - no redness or discharge. "
        "Eating a normal dinner. Levetiracetam 2000 given."
    ),
    "episodes": [
        _ep(1, "Low-grade temp 37.8 settled to 37.2 with paracetamol; wounds reviewed, no redness or discharge; ate normal dinner; levetiracetam given.",
            ["vitals", "wound", "meals"], "routine"),
    ],
}
WARD[(7, 6)] = {
    "note": (
        "Afebrile overnight. Slept well, no analgesia required after midnight. Up to the bathroom independently."
    ),
    "episodes": [
        _ep(1, "Afebrile overnight; slept well, no analgesia after midnight; independent to bathroom.",
            ["vitals", "sleep", "mobility"], "routine"),
    ],
}
WARD[(7, 7)] = {
    "note": (
        "Bowels open this morning. Full diet, eating well. Pain 1-2/10. "
        "Keen to go home; team wants one more day of observation given the seizure history."
    ),
    "episodes": [
        _ep(1, "Bowels open; full diet, eating well; pain 1-2/10; team keeping one more observation day.",
            ["meals", "pain"], "routine"),
    ],
}
WARD[(7, 8)] = {
    "note": (
        "Comfortable evening, walked laps of the corridor with his brother visiting. "
        "Pain 1/10. Levetiracetam 2000 given and charted."
    ),
    "episodes": [
        _ep(1, "Walked corridor laps with visiting brother; pain 1/10; levetiracetam 2000 given.",
            ["mobility", "pain"], "routine"),
    ],
}
WARD[(7, 9)] = {
    "note": (
        "Unremarkable night, slept through. Morning obs stable, wounds clean."
    ),
    "episodes": [
        _ep(1, "Slept through the night; obs stable; wounds clean.",
            ["sleep", "vitals", "wound"], "routine"),
    ],
}
WARD[(7, 10)] = {
    "note": (
        "Day team reviewed - clinically ready, staying while social work confirms home support for the seizure plan. "
        "Showered independently, dressing removed, sites healing."
    ),
    "episodes": [
        _ep(1, "Clinically ready; awaiting social work confirmation of home support; showered independently; sites healing.",
            ["wound", "mobility"], "routine"),
    ],
}
WARD[(7, 11)] = {
    "note": (
        "Quiet evening, ate a full dinner, watched football in the day room. Pain nil at rest."
    ),
    "episodes": [
        _ep(1, "Ate full dinner; watched football in day room; pain nil at rest.",
            ["meals", "pain"], "routine"),
    ],
}
WARD[(7, 12)] = {
    "note": (
        "Slept well. One waking at 0500, mobilised to bathroom without issue. Morning medications including levetiracetam given on time."
    ),
    "episodes": [
        _ep(1, "Slept well, one 0500 waking, bathroom without issue; morning meds incl. levetiracetam on time.",
            ["sleep", "mobility"], "routine"),
    ],
}
WARD[(7, 13)] = {
    "note": (
        "Social work confirmed support at home. Discharge planned for tomorrow with GP letter and neurology follow-up. Eating and mobilising fully."
    ),
    "episodes": [
        _ep(1, "Social work confirmed home support; discharge planned tomorrow with GP letter and neurology follow-up.",
            ["mobility", "meals"], "routine"),
    ],
}
WARD[(7, 14)] = {
    "note": (
        "Evening uneventful. Packed his bag, keen for the morning. Levetiracetam 2000 given; discharge scripts checked."
    ),
    "episodes": [
        _ep(1, "Uneventful evening; discharge scripts checked; levetiracetam 2000 given.",
            ["meals"], "routine"),
    ],
}
WARD[(7, 15)] = {
    "note": (
        "Slept soundly. Morning obs stable. Ready for discharge paperwork after breakfast."
    ),
    "episodes": [
        _ep(1, "Slept soundly; obs stable; ready for discharge paperwork after breakfast.",
            ["sleep", "vitals"], "routine"),
    ],
}

# ===================================================================== #
# BED 9 — June Park, 52F. Left lower-leg cellulitis. HERO BED.
# Planted: IV-site red herring (s1, resolved s2); cefazolin order (s4);
# erythema mention (s6, night); "red patches" recurrence (s12, night).
# Three phrasings, one thread: erythema / red patches / rash.
# ===================================================================== #

WARD[(9, 1)] = {
    "note": (
        "Admitted with left lower-leg cellulitis, margins marked at 1000, leg elevated on two pillows. Pain 4/10. "
        "IV site in the left forearm slightly red at the hub, flushing well - watching it. "
        "Baseline obs: temp 37.8, HR 92, BP 128/76."
    ),
    "episodes": [
        _ep(1, "Left leg cellulitis: margins marked 1000, leg elevated, pain 4/10; temp 37.8, HR 92, BP 128/76.",
            ["cellulitis", "pain", "vitals"], "routine"),
        _ep(2, "IV site left forearm slightly red at the hub, flushing well - watching.",
            ["iv_site"], "condition",
            why_hint="re-check IV site each round; resite if redness spreads"),
    ],
}
WARD[(9, 2)] = {
    "note": (
        "Old IV removed and resited to the right hand at 1830; the left forearm site has settled, no redness or tracking - considering that concern resolved. "
        "Leg margins unchanged from morning marking. Pain 3/10 with elevation."
    ),
    "episodes": [
        _ep(1, "Old IV removed, resited to right hand 1830; left forearm site settled, no redness or tracking - concern resolved.",
            ["iv_site"], "resolved", type="resolution", resolves="iv_site"),
        _ep(2, "Leg margins unchanged from morning; pain 3/10 with elevation.",
            ["cellulitis", "pain"], "routine"),
    ],
}
WARD[(9, 3)] = {
    "note": (
        "Slept reasonably with the leg elevated, one waking for analgesia at 0230. "
        "Margins stable at the 0600 check, warmth unchanged. Temp 37.6."
    ),
    "episodes": [
        _ep(1, "Slept with leg elevated, one 0230 analgesia waking; margins stable 0600, temp 37.6.",
            ["sleep", "cellulitis", "vitals"], "routine"),
    ],
}
WARD[(9, 4)] = {
    "note": (
        "Cefazolin 1 g IV every 8 hours started this morning for the cellulitis, first dose at 0930, tolerated. "
        "Margins look to be receding a few millimetres from the marked line. Pain 3/10. Eating normally."
    ),
    "episodes": [
        _ep(1, "Cefazolin 1 g IV q8h started for cellulitis; first dose 0930, tolerated.",
            ["cefazolin"], "condition", type="order",
            why_hint="cefazolin q8h - doses fall at 0600/1400/2200; 0200 hang on nights when schedule shifts"),
        _ep(2, "Margins receding a few millimetres from marked line; pain 3/10; eating normally.",
            ["cellulitis", "pain", "meals"], "routine"),
    ],
}
WARD[(9, 5)] = {
    "note": (
        "Comfortable evening, temp down to 37.4. Leg less tender to touch, elevation maintained. "
        "Ate most of dinner, mobilising to the bathroom with the drip stand."
    ),
    "episodes": [
        _ep(1, "Temp 37.4; leg less tender, elevation maintained; ate most of dinner; mobilising with drip stand.",
            ["vitals", "cellulitis", "meals", "mobility"], "routine"),
    ],
}
WARD[(9, 6)] = {
    "note": (
        "Overnight largely settled, analgesia once at 0100. "
        "During the 0200 turn I noted faint erythema across the right forearm - new since yesterday, not at the old or current IV sites; possibly related to the antibiotic started Tuesday. Will monitor. "
        "Leg itself continues to improve, margins stable."
    ),
    "episodes": [
        _ep(1, "Faint erythema across the right forearm noted during 0200 turn - new since yesterday, not at old or current IV sites; possibly related to the antibiotic started Tuesday; will monitor.",
            ["skin_reaction", "cefazolin"], "critical",
            why_hint="possible drug reaction - verify skin status before the next cefazolin dose"),
        _ep(2, "Night settled, analgesia once 0100; leg margins stable and improving.",
            ["sleep", "cellulitis"], "routine"),
    ],
}
WARD[(9, 7)] = {
    "note": (
        "Margins clearly receding, about 2 cm inside the original line now. CRP trending down per morning bloods. "
        "Pain 2/10. Walked the corridor with the drip stand."
    ),
    "episodes": [
        _ep(1, "Margins receding ~2 cm inside original line; CRP trending down; pain 2/10; walked corridor with drip stand.",
            ["cellulitis", "pain", "mobility"], "routine"),
    ],
}
WARD[(9, 8)] = {
    "note": (
        "Settled evening. Cefazolin 2200 dose given, tolerated. Leg warm but visibly better. "
        "Ate well, family video call after supper."
    ),
    "episodes": [
        _ep(1, "Cefazolin 2200 dose tolerated; leg visibly better; ate well.",
            ["cellulitis", "meals"], "routine"),
    ],
}
WARD[(9, 9)] = {
    "note": (
        "Slept well, afebrile overnight, obs stable. Leg elevation maintained; no complaints at the 0600 check."
    ),
    "episodes": [
        _ep(1, "Slept well, afebrile; obs stable; leg elevation maintained.",
            ["sleep", "vitals", "cellulitis"], "routine"),
    ],
}
WARD[(9, 10)] = {
    "note": (
        "Leg redness much reduced, margins well inside the line. Team pleased on rounds; talking about switching to oral antibiotics in a day or two. Pain 1/10."
    ),
    "episodes": [
        _ep(1, "Leg redness much reduced, margins well inside line; oral switch being discussed; pain 1/10.",
            ["cellulitis", "pain"], "routine"),
    ],
}
WARD[(9, 11)] = {
    "note": (
        "Quiet evening, ate a full dinner. Sister visited. Mobilising freely with the drip stand, steady."
    ),
    "episodes": [
        _ep(1, "Ate full dinner; sister visited; mobilising freely with drip stand.",
            ["meals", "mobility"], "routine"),
    ],
}
WARD[(9, 12)] = {
    "note": (
        "At the 0400 round there are red patches on the right forearm again - small, flat, not raised; she woke and asked whether it was a rash. No itch, no airway symptoms, obs unchanged. "
        "Next cefazolin due at 0600. Leg itself looks excellent."
    ),
    "episodes": [
        _ep(1, "Red patches on the right forearm again at 0400 - small, flat, not raised; patient asked if it was a rash; no itch or airway symptoms.",
            ["skin_reaction", "cefazolin"], "critical",
            why_hint="next cefazolin dose due 0200 tonight - confirm reaction status before it is hung"),
        _ep(2, "Obs unchanged overnight; leg looks excellent.",
            ["vitals", "cellulitis"], "routine"),
    ],
}
WARD[(9, 13)] = {
    "note": (
        "Leg nearly back to normal colour, margins faint. Mobilising independently around the bay. Pain nil to 1/10. Bloods for tomorrow ordered."
    ),
    "episodes": [
        _ep(1, "Leg nearly normal colour, margins faint; mobilising independently; pain 0-1/10.",
            ["cellulitis", "mobility", "pain"], "routine"),
    ],
}
WARD[(9, 14)] = {
    "note": (
        "Evening comfortable. Team planning the switch to oral antibiotics tomorrow if bloods hold. Ate well, watched a film with her sister."
    ),
    "episodes": [
        _ep(1, "Oral antibiotic switch planned tomorrow if bloods hold; ate well.",
            ["meals"], "routine"),
    ],
}
WARD[(9, 15)] = {
    "note": (
        "Comfortable night, slept from 2330 with brief wakings at rounds. Obs stable, afebrile. Handover due to the incoming team this morning."
    ),
    "episodes": [
        _ep(1, "Comfortable night, brief wakings at rounds; obs stable, afebrile; handover due this morning.",
            ["sleep", "vitals"], "routine"),
    ],
}

# ===================================================================== #
# BED 11 — Rose Ngata, 81F. CHF exacerbation. Condition thread:
# fluid_status weights trending down s1 -> s13 (consolidation showcase).
# ===================================================================== #

WARD[(11, 1)] = {
    "note": (
        "Admitted with decompensated heart failure - breathless on minimal exertion, bilateral ankle swelling. On IV furosemide, strict fluid balance, 1.5 L restriction. "
        "Admission weight 82.4 kg. O2 at 2 L, sats 94%. Sleeping propped on three pillows."
    ),
    "episodes": [
        _ep(1, "Admitted with decompensated heart failure; IV furosemide, strict fluid balance, 1.5 L restriction; O2 2 L, sats 94%; sleeps propped on three pillows.",
            ["breathing", "oxygen", "sleep"], "routine"),
        _ep(2, "Admission weight 82.4 kg - daily weights and strict intake/output charting for diuresis.",
            ["fluid_status"], "condition",
            why_hint="weigh before breakfast; escalate if weight rises or urine output drops"),
    ],
}
WARD[(11, 2)] = {
    "note": (
        "Good diuresis this evening, urine output well ahead of intake. Breathing more comfortable at rest. "
        "Ankles still swollen, legs elevated on a footstool while sitting out."
    ),
    "episodes": [
        _ep(1, "Good diuresis, output ahead of intake; breathing more comfortable at rest; ankles swollen, legs elevated.",
            ["fluid_status", "breathing"], "routine"),
    ],
}
WARD[(11, 3)] = {
    "note": (
        "Slept propped up, two toilet trips overnight (expected with diuretic timing). Sats 94% on 2 L. No overnight breathlessness."
    ),
    "episodes": [
        _ep(1, "Slept propped, two toilet trips overnight; sats 94% on 2 L; no overnight breathlessness.",
            ["sleep", "oxygen", "breathing"], "routine"),
    ],
}
WARD[(11, 4)] = {
    "note": (
        "Weight 81.6 kg this morning - down 0.8 kg since admission, diuresis on track. "
        "Walked to the bathroom with one rest, less breathless than yesterday. Ankle swelling reduced."
    ),
    "episodes": [
        _ep(1, "Weight 81.6 kg, down 0.8 kg since admission - diuresis on track; ankle swelling reduced.",
            ["fluid_status"], "condition",
            why_hint="continue daily weights - trend is the signal"),
        _ep(2, "Walked to bathroom with one rest; less breathless than yesterday.",
            ["mobility", "breathing"], "routine"),
    ],
}
WARD[(11, 5)] = {
    "note": (
        "Comfortable evening within the fluid restriction; family reminded about the water jug rules. Ate a low-salt dinner, most of it. Sats 95% on 2 L."
    ),
    "episodes": [
        _ep(1, "Within fluid restriction, family reminded re water jug; ate most of low-salt dinner; sats 95% on 2 L.",
            ["fluid_status", "meals", "oxygen"], "routine"),
    ],
}
WARD[(11, 6)] = {
    "note": (
        "Settled night, one toilet trip, slept propped. Morning sats 95% on 2 L, trial on 1 L planned for the day shift."
    ),
    "episodes": [
        _ep(1, "Settled night, one toilet trip; sats 95% on 2 L; 1 L trial planned for day shift.",
            ["sleep", "oxygen"], "routine"),
    ],
}
WARD[(11, 7)] = {
    "note": (
        "Weight 81.1 kg - steady daily loss, oedema visibly less at both ankles. "
        "O2 weaned to 1 L, sats 94-95%. Walked the corridor slowly with the physio, one rest stop."
    ),
    "episodes": [
        _ep(1, "Weight 81.1 kg, steady daily loss; ankle oedema visibly less.",
            ["fluid_status"], "condition"),
        _ep(2, "O2 weaned to 1 L, sats 94-95%; walked corridor slowly with physio, one rest.",
            ["oxygen", "mobility"], "routine"),
    ],
}
WARD[(11, 8)] = {
    "note": (
        "Quiet evening. Respecting the restriction well; mouth care for thirst. Grandchildren visited briefly, lifted her mood. Sats 95% on 1 L."
    ),
    "episodes": [
        _ep(1, "Fluid restriction respected, mouth care for thirst; grandchildren visited; sats 95% on 1 L.",
            ["fluid_status", "oxygen"], "routine"),
    ],
}
WARD[(11, 9)] = {
    "note": (
        "Slept propped with good stretches, one toilet trip. No nocturnal breathlessness. Morning sats 95% on 1 L."
    ),
    "episodes": [
        _ep(1, "Slept propped in good stretches, one toilet trip; no nocturnal breathlessness; sats 95% on 1 L.",
            ["sleep", "breathing", "oxygen"], "routine"),
    ],
}
WARD[(11, 10)] = {
    "note": (
        "Weight 80.8 kg. Switched from IV to oral furosemide this morning - watching that the trend holds on tablets. "
        "Off oxygen since mid-morning, sats 94% on room air at rest."
    ),
    "episodes": [
        _ep(1, "Weight 80.8 kg; switched IV to oral furosemide - watch that the downward trend holds on tablets.",
            ["fluid_status"], "condition",
            why_hint="first days on oral diuretic - a weight rise means the switch is failing"),
        _ep(2, "Off oxygen since mid-morning; sats 94% room air at rest.",
            ["oxygen"], "routine"),
    ],
}
WARD[(11, 11)] = {
    "note": (
        "Comfortable on room air all evening, sats 94%. Ate her low-salt dinner. Watched the news with her son."
    ),
    "episodes": [
        _ep(1, "Room air all evening, sats 94%; ate low-salt dinner; son visited.",
            ["oxygen", "meals"], "routine"),
    ],
}
WARD[(11, 12)] = {
    "note": (
        "Good night on two pillows now rather than three. One toilet trip. Sats 94% room air overnight."
    ),
    "episodes": [
        _ep(1, "Slept on two pillows (down from three); one toilet trip; sats 94% RA overnight.",
            ["sleep", "oxygen"], "routine"),
    ],
}
WARD[(11, 13)] = {
    "note": (
        "Weight 80.7 kg - stable on oral furosemide for three days, target reached per the team. "
        "Walked the corridor without a rest stop for the first time. Discharge planning with daughter this afternoon."
    ),
    "episodes": [
        _ep(1, "Weight 80.7 kg, stable on oral furosemide x3 days - target reached.",
            ["fluid_status"], "condition"),
        _ep(2, "Walked corridor without a rest for the first time; discharge planning with daughter.",
            ["mobility"], "routine"),
    ],
}
WARD[(11, 14)] = {
    "note": (
        "Settled evening. Dietitian reviewed the low-salt plan for home. Ate well, fluids within restriction."
    ),
    "episodes": [
        _ep(1, "Dietitian reviewed low-salt plan for home; ate well; fluids within restriction.",
            ["meals", "fluid_status"], "routine"),
    ],
}
WARD[(11, 15)] = {
    "note": (
        "Comfortable night on two pillows, sats 94% room air. Morning weight due before breakfast; discharge checklist started."
    ),
    "episodes": [
        _ep(1, "Comfortable night, two pillows; sats 94% RA; morning weight due; discharge checklist started.",
            ["sleep", "oxygen"], "routine"),
    ],
}

# ===================================================================== #
# BED 12 — Sam Alvarez, 59M. COPD exacerbation. Condition thread:
# prednisone taper (s2, s8). Otherwise routine arc to discharge prep.
# ===================================================================== #

WARD[(12, 1)] = {
    "note": (
        "Admitted with a COPD exacerbation - wheezy, speaking in short sentences on arrival, much better after back-to-back nebulisers. "
        "On salbutamol/ipratropium nebs every 6 hours, sats 90-92% on 1 L (his baseline runs low). Long smoking history, keen to talk about quitting."
    ),
    "episodes": [
        _ep(1, "COPD exacerbation: improved after back-to-back nebs; on salbutamol/ipratropium q6h; sats 90-92% on 1 L (low baseline); keen to discuss quitting smoking.",
            ["breathing", "oxygen"], "routine"),
    ],
}
WARD[(12, 2)] = {
    "note": (
        "Started prednisone 40 mg daily - day 1 of a 5-day course, charted for mornings. "
        "Evening nebs given, breathing comfortable in the chair. Ate a full dinner."
    ),
    "episodes": [
        _ep(1, "Prednisone 40 mg daily started - day 1 of 5-day course, morning dosing.",
            ["steroids"], "condition", type="order",
            why_hint="steroid course must complete - watch glucose and sleep disturbance"),
        _ep(2, "Evening nebs given; breathing comfortable in chair; ate full dinner.",
            ["breathing", "meals"], "routine"),
    ],
}
WARD[(12, 3)] = {
    "note": (
        "Wheezy spell at 0200 settled with a neb and sitting upright; slept lightly afterwards. Sats held 91% on 1 L."
    ),
    "episodes": [
        _ep(1, "Wheezy spell 0200 settled with neb and upright positioning; light sleep after; sats 91% on 1 L.",
            ["breathing", "sleep", "oxygen"], "routine"),
    ],
}
WARD[(12, 4)] = {
    "note": (
        "Better day - nebs spaced to 8-hourly, walking to the day room without stopping. Sats 92% on 1 L. Smoking-cessation counsellor visited, patches started."
    ),
    "episodes": [
        _ep(1, "Nebs spaced to q8h; walked to day room without stopping; sats 92% on 1 L; nicotine patches started.",
            ["breathing", "mobility", "oxygen"], "routine"),
    ],
}
WARD[(12, 5)] = {
    "note": (
        "Comfortable evening, one neb at 1800. Ate well. Reports steroids make him 'buzzy' at night - warned this is common and short-lived."
    ),
    "episodes": [
        _ep(1, "One neb 1800; ate well; feels 'buzzy' on steroids at night - reassured, common and short-lived.",
            ["breathing", "meals", "sleep"], "routine"),
    ],
}
WARD[(12, 6)] = {
    "note": (
        "Broken sleep (steroid-related restlessness), read until 0300 then dozed. No overnight wheeze. Morning sats 92% on 1 L."
    ),
    "episodes": [
        _ep(1, "Broken sleep from steroid restlessness, read until 0300; no overnight wheeze; sats 92% on 1 L.",
            ["sleep", "breathing", "oxygen"], "routine"),
    ],
}
WARD[(12, 7)] = {
    "note": (
        "Trial off oxygen from 0900 - sats 90-91% on room air, acceptable for his baseline per the team. Inhaler technique session booked. Walked two corridor laps."
    ),
    "episodes": [
        _ep(1, "Trial off O2: sats 90-91% RA, acceptable for baseline; inhaler technique session booked; walked two laps.",
            ["oxygen", "breathing", "mobility"], "routine"),
    ],
}
WARD[(12, 8)] = {
    "note": (
        "Prednisone taper progressing - day 3 of 5 taken this morning, no glucose issues on spot checks. "
        "Evening comfortable on room air, sats 91%."
    ),
    "episodes": [
        _ep(1, "Prednisone day 3 of 5 taken; spot glucose checks unremarkable.",
            ["steroids"], "condition"),
        _ep(2, "Comfortable on room air, sats 91%.",
            ["oxygen", "breathing"], "routine"),
    ],
}
WARD[(12, 9)] = {
    "note": (
        "Slept better than previous nights, one neb at 0400 for mild tightness with good effect. Sats 91% room air."
    ),
    "episodes": [
        _ep(1, "Slept better; one 0400 neb for mild tightness, good effect; sats 91% RA.",
            ["sleep", "breathing", "oxygen"], "routine"),
    ],
}
WARD[(12, 10)] = {
    "note": (
        "Inhaler technique session done - technique corrected, spacer provided and teach-back successful. Walking freely, sats 91-92% room air."
    ),
    "episodes": [
        _ep(1, "Inhaler technique corrected, spacer provided, teach-back successful; walking freely; sats 91-92% RA.",
            ["breathing", "mobility"], "routine"),
    ],
}
WARD[(12, 11)] = {
    "note": (
        "Comfortable evening. Ate a full dinner, no wheeze on walking to the bathroom. Planning home nebuliser conversation for tomorrow."
    ),
    "episodes": [
        _ep(1, "Ate full dinner; no wheeze on walking; home nebuliser conversation planned tomorrow.",
            ["meals", "breathing"], "routine"),
    ],
}
WARD[(12, 12)] = {
    "note": (
        "Reasonable night, brief tight spell self-managed with the spacer - technique holding. Sats 91% room air overnight."
    ),
    "episodes": [
        _ep(1, "Brief tight spell self-managed with spacer; sats 91% RA overnight.",
            ["breathing", "sleep", "oxygen"], "routine"),
    ],
}
WARD[(12, 13)] = {
    "note": (
        "Prednisone course completed today (day 5 of 5). Discharge checklist started: GP letter, inhaler plan, cessation follow-up. Sats stable 92% room air."
    ),
    "episodes": [
        _ep(1, "Prednisone course completed (day 5/5); discharge checklist started (GP letter, inhaler plan, cessation follow-up); sats 92% RA.",
            ["steroids", "breathing"], "routine"),
    ],
}
WARD[(12, 14)] = {
    "note": (
        "Settled evening, no nebs needed since morning - using his own inhaler with the spacer. Ate well; family bringing clothes for discharge."
    ),
    "episodes": [
        _ep(1, "No nebs since morning, using own inhaler with spacer; ate well; discharge clothes arranged.",
            ["breathing", "meals"], "routine"),
    ],
}
WARD[(12, 15)] = {
    "note": (
        "Slept well, no overnight wheeze or nebs. Morning sats 92% on room air. Ready for discharge review after breakfast."
    ),
    "episodes": [
        _ep(1, "Slept well, no overnight wheeze or nebs; sats 92% RA; discharge review after breakfast.",
            ["sleep", "breathing", "oxygen"], "routine"),
    ],
}

# ===================================================================== #
# Ground truth (SEED_DATA.md "Rules"): per-shift critical items drive
# recall@5; the expiry schedule drives forgetting precision.
# active_from_shift = the first *brief* (incoming shift) that must
# contain the item, i.e. evidence shift + 1.
# ===================================================================== #

THREADS = [
    {
        "id": "warfarin-bleeding-risk",
        "bed": 3,
        "kind": "critical",
        "label": "On warfarin for AF — bleeding risk",
        "evidence": ["ep-03-01-2", "ep-03-10-1"],
        "active_from_shift": 2,
        "resolved_at_shift": None,
    },
    {
        "id": "penicillin-allergy",
        "bed": 5,
        "kind": "critical",
        "label": "Documented penicillin allergy (hives, lip swelling)",
        "evidence": ["ep-05-01-2"],
        "active_from_shift": 2,
        "resolved_at_shift": None,
    },
    {
        "id": "seizure-precautions",
        "bed": 7,
        "kind": "critical",
        "label": "Seizure history — levetiracetam + precautions",
        "evidence": ["ep-07-01-2"],
        "active_from_shift": 2,
        "resolved_at_shift": None,
    },
    {
        "id": "cefazolin-reaction",
        "bed": 9,
        "kind": "critical",
        "label": "Possible cefazolin reaction — erythema/red patches after start",
        # evidence = the REACTION observations. The s4 med-start order is
        # thread context (and is cited by the consolidated memory), but
        # surfacing "cefazolin started" alone does NOT convey the reaction,
        # so it must not count as recall — for either system.
        "evidence": ["ep-09-06-1", "ep-09-12-1"],
        "active_from_shift": 7,
        "resolved_at_shift": None,
    },
    {
        "id": "falls-risk",
        "bed": 3,
        "kind": "critical",
        "label": "Swallowed falls-risk mention — unsteady to bathroom",
        "evidence": ["ep-03-07-2"],
        "active_from_shift": 8,
        "resolved_at_shift": None,
    },
    {
        "id": "sleep-conflict",
        "bed": 5,
        "kind": "contradiction",
        "label": "Conflicting sleep reports (day vs night nurse)",
        "evidence": ["ep-05-10-2", "ep-05-12-1"],
        "active_from_shift": 13,
        "resolved_at_shift": None,
    },
]

EXPIRY = [
    {
        "thread": "iv-site-red-herring",
        "bed": 9,
        "label": "IV-site concern resolved shift 2 — must never resurface",
        "episodes": ["ep-09-01-2", "ep-09-02-1"],
        "resolved_at_shift": 2,
        "must_not_surface_from_shift": 3,
    },
]
