#!/usr/bin/env python3
"""Fictitious Labs QA Simulator — scenario generator.

Produces one scenario package for an A280 assay of an FL-101 lot:
a completed FRM-QC-101 worksheet, a plain raw data sheet, and a
ground-truth file listing every planted fault. The worksheet is filled
FROM the raw data, so the clean case agrees everywhere; faults are
injected at specific fields from the v1 registry below.

Deterministic: same seed + same fault selection -> byte-identical
output. Pure Python, stdlib only. No timestamps are taken from the
clock; all dates derive from the seed.

Scope (settled, see ../DESIGN.md): faults are documentation and
transcription errors only — every fault is detectable by COMPARING
documents, never by recomputing a result.
"""

import argparse
import json
import os
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

# --- World facts (mirror of ../company-profile.md — the ledger wins) ---
E1PC = Decimal("1.42")            # TM-QC-101 extinction coefficient E 1%
DILUTION_LABEL = "1:10"
CURRENT_METHOD = "TM-QC-101 v3.0"
SUPERSEDED_METHOD = "TM-QC-101 v2.0"
CURRENT_RANGE = "9.0 – 11.0"
SUPERSEDED_RANGE = "8.5 – 11.5"
INSTRUMENT = "UV-02"
ANALYSTS = [("J. Park", "JP"), ("R. Osei", "RO")]
QC_REVIEWER_INITIALS = "SD"       # S. Delgado
QA_REVIEWER_INITIALS = "MW"       # M. Whitfield

# Worksheet fields, in FRM-QC-101 order: (key, label)
FIELDS = [
    ("sample_id", "Sample ID"),
    ("lot_number", "Lot number"),
    ("analysis_date", "Date of analysis"),
    ("analyst", "Analyst"),
    ("method_version", "Method / version"),
    ("instrument_id", "Instrument ID"),
    ("dilution", "Dilution performed"),
    ("blank_initials", "Blank confirmed (initials)"),
    ("reading_1", "Reading 1 (AU)"),
    ("reading_2", "Reading 2 (AU)"),
    ("reading_3", "Reading 3 (AU)"),
    ("reported_result", "Reported result (mg/mL)"),
    ("acceptance_criterion", "Acceptance criterion (mg/mL)"),
    ("within_criterion", "Result within criterion? (Y/N)"),
    ("verification", "Second-person verification (initials/date)"),
    ("qa_review", "QA review (initials/date)"),
]
FIELD_LABELS = dict(FIELDS)

# v1 fault registry: fault_type -> plain-words category for the trainee
CATEGORIES = {
    "transcription_value": "Value doesn't match the raw data",
    "lot_mismatch": "Lot number doesn't match",
    "missing_initials": "Missing initials",
    "bad_correction": "Correction made incorrectly",
    "wrong_precision": "Result reported with the wrong precision",
    "superseded_version": "Superseded method version used",
    "date_sequence": "Dates out of sequence",
    "blank_required": "Required field left blank",
}
FAULT_TYPES = list(CATEGORIES)


def _round_half_up(value, places):
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _result_from_readings(readings):
    """Concentration (mg/mL) from AU readings: average, apply the 1:10
    dilution and E 1%, round once to one decimal (SOP-QA-002)."""
    avg = sum(readings) / Decimal(len(readings))
    conc = avg * Decimal(100) / E1PC
    return conc, _round_half_up(conc, "0.1")


def _transpose_last_digits(text):
    idx = [i for i, ch in enumerate(text) if ch.isdigit()]
    i, j = idx[-2], idx[-1]
    chars = list(text)
    chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def build_scenario(seed, faults, scenario_id):
    faults = list(faults)
    unknown = [f for f in faults if f not in FAULT_TYPES]
    if unknown:
        raise ValueError(f"unknown fault type(s): {', '.join(unknown)}")

    rng = random.Random(seed)

    # --- Baseline facts (correct by construction) ---
    analyst_name, analyst_initials = ANALYSTS[rng.randrange(len(ANALYSTS))]
    lot = f"FL101-2611-{rng.randrange(1, 60):03d}"
    sample = f"QC-2026-{rng.randrange(100, 400):04d}"
    analysis = date(2026, 11, 16) + timedelta(days=rng.randrange(0, 4))
    receipt = analysis - timedelta(days=rng.randrange(1, 3))
    verification_date = analysis
    qa_date = analysis + timedelta(days=rng.randrange(1, 3))

    if "superseded_version" in faults:
        # Fixed readings whose result is 8.7 mg/mL: passes the superseded
        # 8.5-11.5 range, fails the current 9.0-11.0 range.
        readings = [Decimal("0.124"), Decimal("0.123"), Decimal("0.124")]
    else:
        target = Decimal(rng.choice(["9.6", "9.8", "10.0", "10.2", "10.4"]))
        a_target = target * E1PC / Decimal(100)
        readings = [
            _round_half_up(
                a_target + Decimal(rng.choice([-1, 0, 1])) / Decimal(1000),
                "0.001",
            )
            for _ in range(3)
        ]
    conc_exact, result = _result_from_readings(readings)
    reading_strs = [f"{r:.3f}" for r in readings]
    result_str = f"{result:.1f}"

    raw_fields = {
        "sample_id": sample,
        "lot_number": lot,
        "receipt_date": receipt.isoformat(),
        "analyst": analyst_name,
        "instrument_id": INSTRUMENT,
        "reading_1": reading_strs[0],
        "reading_2": reading_strs[1],
        "reading_3": reading_strs[2],
        "reported_result": result_str,
    }

    ws = {
        "sample_id": sample,
        "lot_number": lot,
        "analysis_date": analysis.isoformat(),
        "analyst": analyst_name,
        "method_version": CURRENT_METHOD,
        "instrument_id": INSTRUMENT,
        "dilution": DILUTION_LABEL,
        "blank_initials": analyst_initials,
        "reading_1": reading_strs[0],
        "reading_2": reading_strs[1],
        "reading_3": reading_strs[2],
        "reported_result": result_str,
        "acceptance_criterion": CURRENT_RANGE,
        "within_criterion": "Y",
        "verification": f"{QC_REVIEWER_INITIALS}, {verification_date.isoformat()}",
        "qa_review": f"{QA_REVIEWER_INITIALS}, {qa_date.isoformat()}",
    }

    planted = []

    # --- Fault injection (fixed order; each fault touches its own field) ---
    if "superseded_version" in faults:
        ws["method_version"] = SUPERSEDED_METHOD
        ws["acceptance_criterion"] = SUPERSEDED_RANGE
        planted.append({
            "field": "method_version",
            "fault_type": "superseded_version",
            "detail": (
                f"Worksheet cites {SUPERSEDED_METHOD} and its "
                f"{SUPERSEDED_RANGE} mg/mL criterion. {CURRENT_METHOD} "
                f"(effective 2026-09-14) superseded it with "
                f"{CURRENT_RANGE} mg/mL; the result {result_str} mg/mL "
                f"fails the current criterion."
            ),
        })

    if "lot_mismatch" in faults:
        wrong_lot = _transpose_last_digits(lot)
        ws["lot_number"] = wrong_lot
        planted.append({
            "field": "lot_number",
            "fault_type": "lot_mismatch",
            "detail": (
                f"Worksheet lot {wrong_lot} does not match the raw data "
                f"sheet lot {lot}."
            ),
        })

    if "transcription_value" in faults:
        wrong = _transpose_last_digits(reading_strs[1])
        ws["reading_2"] = wrong
        planted.append({
            "field": "reading_2",
            "fault_type": "transcription_value",
            "detail": (
                f"Reading 2 on the worksheet ({wrong}) does not match "
                f"the raw data sheet ({reading_strs[1]})."
            ),
        })

    if "wrong_precision" in faults:
        precise = str(_round_half_up(conc_exact, "0.01"))
        ws["reported_result"] = precise
        planted.append({
            "field": "reported_result",
            "fault_type": "wrong_precision",
            "detail": (
                f"Reported result on the worksheet ({precise}) carries "
                f"two decimal places; SOP-QA-002 and TM-QC-101 require "
                f"one decimal place ({result_str})."
            ),
        })

    if "bad_correction" in faults:
        ws["reading_1"] = f"{reading_strs[0]} †"
        planted.append({
            "field": "reading_1",
            "fault_type": "bad_correction",
            "detail": (
                "Reading 1 was corrected by obliteration (correction "
                "fluid; original entry not legible), with no line-through, "
                "initials, or date — prohibited by SOP-QA-001 §4.3."
            ),
        })

    if "missing_initials" in faults:
        ws["blank_initials"] = ""
        planted.append({
            "field": "blank_initials",
            "fault_type": "missing_initials",
            "detail": (
                "Blank confirmation initials are absent; the blank check "
                "is not attributable to anyone (SOP-QA-001 §4.2)."
            ),
        })

    if "blank_required" in faults:
        ws["instrument_id"] = ""
        planted.append({
            "field": "instrument_id",
            "fault_type": "blank_required",
            "detail": (
                "Instrument ID is blank. A required field is never left "
                "blank; a non-applicable field is entered as N/A with "
                "initials and date (SOP-QA-001 §4.2)."
            ),
        })

    if "date_sequence" in faults:
        early = analysis - timedelta(days=1)
        ws["qa_review"] = f"{QA_REVIEWER_INITIALS}, {early.isoformat()}"
        planted.append({
            "field": "qa_review",
            "fault_type": "date_sequence",
            "detail": (
                f"QA review is dated {early.isoformat()}, before the "
                f"analysis date {analysis.isoformat()} — a review cannot "
                f"precede the work it reviews."
            ),
        })

    # --- Render trainee-facing documents ---
    ws_lines = [
        "# FRM-QC-101 — A280 Assay Worksheet (completed record)",
        "",
        "**Fictitious Labs Inc.** · Form version 2.0 · "
        "Controlled form for TM-QC-101",
        "",
        "| Field | Entry |",
        "|---|---|",
    ]
    for key, label in FIELDS:
        ws_lines.append(f"| {label} | {ws[key]} |")
    if "bad_correction" in faults:
        ws_lines += [
            "",
            "† Entry rewritten over correction fluid; the original "
            "entry is not legible.",
        ]
    worksheet_md = "\n".join(ws_lines) + "\n"

    raw_lines = [
        "# Raw Data Sheet — UV absorbance readings",
        "",
        "**Fictitious Labs Inc.** · Plain record of readings, as taken. "
        "Transcribe exactly.",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Sample ID | {raw_fields['sample_id']} |",
        f"| Lot number | {raw_fields['lot_number']} |",
        f"| Date received | {raw_fields['receipt_date']} |",
        f"| Analyst | {raw_fields['analyst']} |",
        f"| Instrument ID | {raw_fields['instrument_id']} |",
        f"| Reading 1 (AU) | {raw_fields['reading_1']} |",
        f"| Reading 2 (AU) | {raw_fields['reading_2']} |",
        f"| Reading 3 (AU) | {raw_fields['reading_3']} |",
        f"| Result (mg/mL) | {raw_fields['reported_result']} |",
    ]
    raw_md = "\n".join(raw_lines) + "\n"

    ground_truth = {
        "scenario_id": scenario_id,
        "seed": seed,
        "sample_id": sample,
        "lot_number": lot,
        "analysis_date": analysis.isoformat(),
        "faults": planted,
    }

    return {
        "scenario_id": scenario_id,
        "seed": seed,
        "worksheet_fields": ws,
        "raw_fields": raw_fields,
        "faults": planted,
        "worksheet_md": worksheet_md,
        "raw_md": raw_md,
        "ground_truth": ground_truth,
    }


def write_scenario(scenario, out_root):
    out_dir = os.path.join(out_root, scenario["scenario_id"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "worksheet.md"), "w", encoding="utf-8") as f:
        f.write(scenario["worksheet_md"])
    with open(os.path.join(out_dir, "raw_data.md"), "w", encoding="utf-8") as f:
        f.write(scenario["raw_md"])
    with open(os.path.join(out_dir, "ground_truth.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(scenario["ground_truth"], indent=2, sort_keys=True) + "\n")
    return out_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--faults", default="",
        help=f"comma-separated fault types; registry: {', '.join(FAULT_TYPES)}",
    )
    parser.add_argument("--id", default=None, help="scenario id (default: scenario-<seed>)")
    parser.add_argument(
        "--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios"),
        help="output root directory",
    )
    args = parser.parse_args()
    fault_list = [f.strip() for f in args.faults.split(",") if f.strip()]
    scenario_id = args.id or f"scenario-{args.seed}"
    scenario = build_scenario(args.seed, fault_list, scenario_id)
    out_dir = write_scenario(scenario, args.out)
    print(f"wrote {out_dir} (seed={args.seed}, faults={len(scenario['faults'])})")


if __name__ == "__main__":
    main()
