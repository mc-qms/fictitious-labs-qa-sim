#!/usr/bin/env python3
"""Fictitious Labs QA Simulator — batch-record scenario generator.

Produces one scenario package for the manufacture of an FL-101 lot:
an executed batch record (reproduced from FRM-MF-101, the master
batch record), the FL-EDMS issuance record for the batch, and a
ground-truth file listing every planted fault. The record is built
correct by construction; faults are injected at specific fields
from the registry below.

Deterministic: same seed + same fault selection -> byte-identical
output. Pure Python, stdlib only. All dates derive from the seed.

Scope (settled, see ../DESIGN.md): faults are documentation and
transcription errors only — every fault is detectable by COMPARING
documents (the record against the issuance record, the label
specimen against the record, the record against the master in the
EDMS), never by recomputing a result.
"""

import argparse
import json
import os
import random
from datetime import date, timedelta

# --- World facts (mirror of ../company-profile.md — the ledger wins) ---
CURRENT_MASTER = "FRM-MF-101 v2.0"
SUPERSEDED_MASTER = "FRM-MF-101 v1.0"
PH_RANGE = "6.9–7.3"               # FRM-MF-101 v2.0, step 2
PH_RANGE_OLD = "6.8–7.4"           # FRM-MF-101 v1.0, step 2
THEORETICAL_YIELD_G = 450
OPERATOR = ("D. Alvarez", "DA")
VERIFIER = ("K. Nguyen", "KN")
QA_ISSUER_INITIALS = "MW"          # M. Whitfield
TOTAL_PAGES = 6

# Record fields, in record order: (key, label)
FIELDS = [
    ("batch_number", "Batch number"),
    ("mbr_version", "Master batch record version"),
    ("inoculation", "Step 1 — Inoculation entry"),
    ("culture_ph", "Step 2 — Culture pH"),
    ("harvest", "Step 3 — Harvest entry"),
    ("purification", "Step 4 — Purification entry"),
    ("filtration_verification", "Step 5 — Filtration verification"),
    ("final_concentration", "Step 5 — Final concentration result"),
    ("summary_concentration", "Batch summary — concentration"),
    ("label_concentration", "Label specimen — concentration"),
    ("label_retest", "Label specimen — retest date"),
    ("page_sequence", "Page sequence (page X of Y)"),
]
FIELD_LABELS = dict(FIELDS)

# Fault registry: fault_type -> plain-words category for the trainee
CATEGORIES = {
    "missing_verification": "Required second-person verification missing",
    "sign_time_sequence": "Verification dated before the step it verifies",
    "summary_transcription": "Summary value doesn't match the step entry",
    "label_mismatch": "Label doesn't match the batch record",
    "blank_step": "Required step entry left blank",
    "page_total_mismatch": "Page count doesn't match the issuance record",
    "superseded_template": "Superseded master version used",
    "missing_step": "Master step missing from the record",
    "out_of_master_range": "Value outside the master batch record range",
}
FAULT_TYPES = list(CATEGORIES)

DIFFICULTY = {
    "missing_verification": "easy",
    "sign_time_sequence": "easy",
    "summary_transcription": "easy",
    "label_mismatch": "easy",
    "blank_step": "easy",
    "page_total_mismatch": "easy",
    "superseded_template": "hard",
    "missing_step": "hard",
    "out_of_master_range": "hard",
}

# Fault pairs that cannot describe the same record.
INCOMPATIBLE = [
    ("superseded_template", "missing_verification"),
    ("superseded_template", "sign_time_sequence"),
    ("missing_verification", "sign_time_sequence"),
]


def _transpose_last_digits(text):
    idx = [i for i, ch in enumerate(text) if ch.isdigit()]
    i, j = idx[-2], idx[-1]
    chars = list(text)
    chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _plus_12_months(d):
    return date(d.year + 1, d.month, d.day)


def build_scenario(seed, faults, scenario_id):
    faults = list(faults)
    unknown = [f for f in faults if f not in FAULT_TYPES]
    if unknown:
        raise ValueError(f"unknown fault type(s): {', '.join(unknown)}")
    for a, b in INCOMPATIBLE:
        if a in faults and b in faults:
            raise ValueError(f"incompatible fault pair: {a} + {b}")

    rng = random.Random(seed)

    # --- Baseline facts (correct by construction) ---
    batch = f"FL101-2611-{rng.randrange(1, 60):03d}"
    start = date(2026, 11, 2) + timedelta(days=rng.randrange(0, 10))
    d_inoc = start
    d_culture = start + timedelta(days=12)
    d_harvest = d_culture
    d_purif = start + timedelta(days=13)
    d_fill = start + timedelta(days=14)
    d_summary = start + timedelta(days=15)
    d_issue = start - timedelta(days=1)
    retest = _plus_12_months(d_fill)

    wcb_lot = f"WCB-2026-{rng.randrange(10, 99):03d}"
    ph = rng.choice(["7.0", "7.1", "7.2"])
    harvest_vol = f"{rng.choice([182.0, 184.0, 185.0, 186.0, 188.0]):.1f}"
    pool_vol = rng.choice([43.5, 44.0, 44.5])
    filled_vol = pool_vol - 1.5
    containers = int(filled_vol / 0.5)
    conc_choices = ["9.6", "9.8", "10.0", "10.2", "10.4"]
    if "summary_transcription" in faults or "label_mismatch" in faults:
        conc_choices.remove("10.0")  # digit transposition must be visible
    conc = rng.choice(conc_choices)
    yield_g = filled_vol * float(conc)
    yield_pct = yield_g / THEORETICAL_YIELD_G * 100

    rec = {
        "batch_number": batch,
        "mbr_version": CURRENT_MASTER,
        "inoculation": f"WCB vial lot {wcb_lot}; performed by {OPERATOR[1]}, "
                       f"{d_inoc.isoformat()}",
        "culture_ph": ph,
        "harvest": f"Harvest volume {harvest_vol} L; performed by "
                   f"{OPERATOR[1]}, {d_harvest.isoformat()}",
        "purification": f"Pool volume {pool_vol:.1f} L; performed by "
                        f"{OPERATOR[1]}, {d_purif.isoformat()}",
        "filtration_verification": f"Verified by {VERIFIER[1]}, "
                                   f"{d_fill.isoformat()}",
        "final_concentration": conc,
        "summary_concentration": conc,
        "label_concentration": conc,
        "label_retest": retest.isoformat(),
        "page_sequence": f"Pages 1–{TOTAL_PAGES} of {TOTAL_PAGES}",
    }
    planted = []

    def plant(field, fault_type, detail):
        planted.append({
            "field": field,
            "fault_type": fault_type,
            "difficulty": DIFFICULTY[fault_type],
            "detail": detail,
        })

    # --- Fault injection (fixed order; each fault touches its own field) ---
    if "superseded_template" in faults:
        rec["mbr_version"] = SUPERSEDED_MASTER
        rec["filtration_verification"] = "(not designated in this version)"
        plant("mbr_version", "superseded_template",
              f"The record was executed on {SUPERSEDED_MASTER}. QA issued "
              f"{CURRENT_MASTER} for this batch (see the issuance record), "
              f"and v1.0 was superseded on 2026-08-17: the culture pH range "
              f"it carries ({PH_RANGE_OLD}) was tightened to {PH_RANGE}, "
              f"and it does not designate independent verification of the "
              f"filtration and fill step.")

    if "out_of_master_range" in faults:
        rec["culture_ph"] = "7.5"
        plant("culture_ph", "out_of_master_range",
              f"Culture pH is recorded as 7.5. The master batch record "
              f"({CURRENT_MASTER}, step 2) sets the acceptable range at "
              f"{PH_RANGE}; 7.5 is outside it, and the record carries no "
              f"deviation reference.")

    if "blank_step" in faults:
        rec["harvest"] = ""
        plant("harvest", "blank_step",
              "The harvest step entry is blank: no volume, no initials, "
              "no date. A required entry is never left blank "
              "(SOP-QA-027 §4.5; FRM-MF-101 completion rules).")

    if "missing_step" in faults:
        rec["purification"] = "(step absent from the record)"
        plant("purification", "missing_step",
              "Step 4, Purification, is missing from the executed record "
              f"entirely. The master batch record ({CURRENT_MASTER}) "
              "requires five steps; this record has four.")

    if "missing_verification" in faults:
        rec["filtration_verification"] = ""
        plant("filtration_verification", "missing_verification",
              "The sterile filtration and bulk fill step carries no "
              "second-person verification. The master batch record "
              f"({CURRENT_MASTER}, step 5) designates that step as "
              "requiring independent verification (SOP-QA-027 §4.4).")

    if "sign_time_sequence" in faults:
        early = d_fill - timedelta(days=1)
        rec["filtration_verification"] = f"Verified by {VERIFIER[1]}, " \
                                         f"{early.isoformat()}"
        plant("filtration_verification", "sign_time_sequence",
              f"Verification of the filtration and fill step is dated "
              f"{early.isoformat()}, the day before the step was performed "
              f"({d_fill.isoformat()}) — a verification cannot precede "
              f"the work it verifies.")

    if "summary_transcription" in faults:
        wrong = _transpose_last_digits(conc)
        rec["summary_concentration"] = wrong
        plant("summary_concentration", "summary_transcription",
              f"The batch summary states a final concentration of "
              f"{wrong} mg/mL; the step 5 entry states {conc} mg/mL. "
              "The summary does not match the record it summarizes.")

    if "label_mismatch" in faults:
        wrong = _transpose_last_digits(conc)
        rec["label_concentration"] = wrong
        plant("label_concentration", "label_mismatch",
              f"The label specimen states a protein concentration of "
              f"{wrong} mg/mL; the batch record states {conc} mg/mL. "
              "Label content is taken from the batch record "
              "(WI-MF-001 §3).")

    if "page_total_mismatch" in faults:
        rec["page_sequence"] = f"Pages 1–{TOTAL_PAGES} of {TOTAL_PAGES - 1}"
        plant("page_sequence", "page_total_mismatch",
              f"Page 4 of the record is footed 'Page 4 of "
              f"{TOTAL_PAGES - 1}', while the issuance record states "
              f"{TOTAL_PAGES} pages and every other page is footed 'of "
              f"{TOTAL_PAGES}' — the record's page integrity does not "
              "check out (SOP-QA-027 §4.3).")

    # --- Render the executed batch record ---
    def footer(page, total=TOTAL_PAGES):
        return f"*Batch {batch} · Page {page} of {total}*"

    page4_total = TOTAL_PAGES - 1 if "page_total_mismatch" in faults \
        else TOTAL_PAGES

    lines = [
        "# Executed Batch Record — FL-101 Drug Substance",
        "",
        "**Fictitious Labs Inc.** · Batch production and control record, "
        "issued under SOP-QA-027",
        "",
        "| Item | Entry |",
        "|---|---|",
        f"| Batch number | {rec['batch_number']} |",
        f"| Master batch record | {rec['mbr_version']} |",
        "| Product | FL-101, monoclonal antibody drug substance |",
        f"| Issued by | {QA_ISSUER_INITIALS} (Quality Assurance), "
        f"{d_issue.isoformat()} |",
        f"| Components used | WCB vial lot {wcb_lot}; basal medium "
        "MED-200; feed medium MED-210; capture resin RES-310; "
        "sterilizing filter FLT-022 |",
        "",
        footer(1),
        "",
        "## Step 1 — Inoculation",
        "",
        f"Entry: {rec['inoculation']}",
        "",
        "## Step 2 — Cell culture",
        "",
        f"Culture pH (day 12): {rec['culture_ph']}",
        f"Performed by {OPERATOR[1]}, {d_culture.isoformat()}",
        "",
        footer(2),
        "",
        "## Step 3 — Harvest",
        "",
        f"Entry: {rec['harvest']}" if rec["harvest"] else
        "Entry: *(blank)*",
        "",
    ]
    if "missing_step" not in faults:
        lines += [
            "## Step 4 — Purification",
            "",
            f"Entry: {rec['purification']}",
            "",
        ]
    lines += [
        footer(3),
        "",
        "## Step 5 — Sterile filtration and bulk fill",
        "",
        f"Containers filled: {containers} × 500 mL; total filled volume "
        f"{filled_vol:.1f} L",
        f"Final protein concentration (TM-QC-101): "
        f"{rec['final_concentration']} mg/mL",
        f"Performed by {OPERATOR[1]}, {d_fill.isoformat()}",
        f"Independent verification: {rec['filtration_verification']}"
        if rec["filtration_verification"] else
        "Independent verification: *(blank)*",
        "",
        footer(4, page4_total),
        "",
        "## Batch summary",
        "",
        "| Item | Entry |",
        "|---|---|",
        f"| Batch number | {batch} |",
        f"| Final protein concentration | "
        f"{rec['summary_concentration']} mg/mL |",
        f"| Total filled volume | {filled_vol:.1f} L |",
        f"| Actual yield | {yield_g:.1f} g ({yield_pct:.1f}% of "
        f"theoretical) |",
        f"| Retest date | {retest.isoformat()} |",
        f"| Summary completed by | {OPERATOR[1]}, "
        f"{d_summary.isoformat()} |",
        "",
        footer(5),
        "",
        "## Label specimen",
        "",
        "Specimen of the labeling applied to the batch containers "
        "(WI-MF-001):",
        "",
        "| Field | Label |",
        "|---|---|",
        "| Product name | FL-101, monoclonal antibody drug substance |",
        f"| Lot number | {batch} |",
        f"| Protein concentration | {rec['label_concentration']} mg/mL |",
        "| Container volume | 500 mL |",
        "| Storage statement | Store at −20 °C ± 5 °C |",
        f"| Retest date | {rec['label_retest']} |",
        "| Statement | For further manufacturing use only |",
        "| Manufacturer | Fictitious Labs Inc. |",
        "",
        footer(6),
        "",
    ]
    record_md = "\n".join(lines)

    issuance_md = "\n".join([
        "# FL-EDMS Issuance Record — Executed Batch Record",
        "",
        "**Fictitious Labs Inc.** · Recorded under SOP-QA-027 §4.3",
        "",
        "| Item | Entry |",
        "|---|---|",
        f"| Batch number | {batch} |",
        f"| Master batch record issued | {CURRENT_MASTER} |",
        f"| Pages | {TOTAL_PAGES} |",
        f"| Issued by | {QA_ISSUER_INITIALS} (Quality Assurance) |",
        f"| Date of issue | {d_issue.isoformat()} |",
        "| Verification | Reproduction verified against the effective "
        "master: every page present and in sequence; every entry field, "
        f"parameter, and limit matches the master. Signed "
        f"{QA_ISSUER_INITIALS}, {d_issue.isoformat()} |",
        "",
    ])

    ground_truth = {
        "family": "batch_record",
        "scenario_id": scenario_id,
        "seed": seed,
        "batch_number": batch,
        "faults": planted,
    }

    return {
        "scenario_id": scenario_id,
        "seed": seed,
        "record_fields": rec,
        "faults": planted,
        "record_md": record_md,
        "issuance_md": issuance_md,
        "ground_truth": ground_truth,
    }


def write_scenario(scenario, out_root):
    out_dir = os.path.join(out_root, scenario["scenario_id"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "batch_record.md"), "w",
              encoding="utf-8") as f:
        f.write(scenario["record_md"])
    with open(os.path.join(out_dir, "issuance.md"), "w",
              encoding="utf-8") as f:
        f.write(scenario["issuance_md"])
    with open(os.path.join(out_dir, "ground_truth.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(scenario["ground_truth"], indent=2,
                           sort_keys=True) + "\n")
    return out_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--faults", default="",
        help=f"comma-separated fault types; registry: "
             f"{', '.join(FAULT_TYPES)}",
    )
    parser.add_argument("--id", default=None,
                        help="scenario id (default: batch-<seed>)")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "scenarios"),
        help="output root directory",
    )
    args = parser.parse_args()
    fault_list = [f.strip() for f in args.faults.split(",") if f.strip()]
    scenario_id = args.id or f"batch-{args.seed}"
    scenario = build_scenario(args.seed, fault_list, scenario_id)
    out_dir = write_scenario(scenario, args.out)
    print(f"wrote {out_dir} (seed={args.seed}, "
          f"faults={len(scenario['faults'])})")


if __name__ == "__main__":
    main()
