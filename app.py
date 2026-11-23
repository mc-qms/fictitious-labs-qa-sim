import streamlit as st

# --- PAGE CONFIGURATION ---
# First, before every other import: the app's name is the first
# thing this app declares (share-preview lesson, Nov 19, 2026).
st.set_page_config(
    page_title="QA Review Simulator — Fictitious Labs",
    page_icon="🔍",
    layout="wide",
)

import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from generator import FIELDS, FIELD_LABELS, CATEGORIES  # noqa: E402
import batch_generator as batch_gen  # noqa: E402
from scorer import score_circles, FP_PENALTY  # noqa: E402

SCENARIOS_DIR = os.path.join(BASE, "scenarios")

REFERENCES = [
    ("SOP-QA-001", "Good Documentation Practices", "v1.0, Effective"),
    ("SOP-QA-002", "Reporting Numerical Values", "v1.0, Effective"),
    ("TM-QC-101", "Protein Concentration by UV Absorbance (A280), FL-101",
     "v3.0, Effective"),
    ("FRM-QC-101", "A280 Assay Worksheet", "v2.0, Effective"),
]

BATCH_REFERENCES = [
    ("SOP-QA-027", "Batch Record Content and Control", "v1.0, Effective"),
    ("FRM-MF-101", "Master Batch Record, FL-101 Drug Substance",
     "v2.0, Effective (v1.0, Superseded)"),
    ("WI-MF-001", "Packaging and Labeling Instructions, FL-101",
     "v1.0, Effective"),
    ("SOP-QA-006", "Batch Record Review and Product Release",
     "v1.0, Effective"),
    ("SOP-QA-001", "Good Documentation Practices", "v1.0, Effective"),
]

EDMS_URL = "https://fictitious-labs-edms.streamlit.app/"


# ------------------------------------------------------------------
# Scenario loading
# ------------------------------------------------------------------

def list_scenarios():
    if not os.path.isdir(SCENARIOS_DIR):
        return []
    return sorted(
        d for d in os.listdir(SCENARIOS_DIR)
        if os.path.isfile(os.path.join(SCENARIOS_DIR, d, "ground_truth.json"))
    )


def load_scenario(scenario_id):
    path = os.path.join(SCENARIOS_DIR, scenario_id)
    with open(os.path.join(path, "ground_truth.json"), encoding="utf-8") as f:
        ground_truth = json.load(f)
    if ground_truth.get("family") == "batch_record":
        with open(os.path.join(path, "batch_record.md"),
                  encoding="utf-8") as f:
            main_md = f.read()
        with open(os.path.join(path, "issuance.md"), encoding="utf-8") as f:
            second_md = f.read()
        return main_md, second_md, ground_truth, "batch_record"
    with open(os.path.join(path, "worksheet.md"), encoding="utf-8") as f:
        worksheet_md = f.read()
    with open(os.path.join(path, "raw_data.md"), encoding="utf-8") as f:
        raw_md = f.read()
    return worksheet_md, raw_md, ground_truth, "a280"


# ------------------------------------------------------------------
# Record parsing: markdown -> ordered blocks of ("md", text) and
# ("entry", field_key, display_text). An entry block is one circleable
# entry of the record under review.
# ------------------------------------------------------------------

def _table_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_table_chrome(cells):
    if not cells:
        return True
    if all(set(c) <= set("-: ") for c in cells):
        return True
    if cells[0] in ("Field", "Item"):
        return True
    return False


def parse_a280(md_text):
    label_to_key = {label: key for key, label in FIELDS}
    blocks = []
    md_buf = []

    def flush():
        if md_buf:
            blocks.append(("md", "\n".join(md_buf)))
            md_buf.clear()

    for line in md_text.splitlines():
        if line.strip().startswith("|"):
            cells = _table_cells(line)
            if len(cells) >= 2 and cells[0] in label_to_key:
                flush()
                entry = cells[1] if cells[1] else "(blank)"
                blocks.append(
                    ("entry", label_to_key[cells[0]],
                     f"{cells[0]} — {entry}"))
                continue
            if _is_table_chrome(cells):
                continue
            md_buf.append(line)
        else:
            md_buf.append(line)
    flush()
    return blocks


# Table-row label -> field key, by table context. The batch summary
# repeats the batch number and the label table repeats the retest
# date, so the maps must be context-specific: each field gets
# exactly one circleable entry in the whole record.
BATCH_HEADER_FIELDS = {
    "Batch number": "batch_number",
    "Master batch record": "mbr_version",
}
BATCH_SUMMARY_FIELDS = {
    "Final protein concentration": "summary_concentration",
}
BATCH_LABEL_FIELDS = {
    "Protein concentration": "label_concentration",
    "Retest date": "label_retest",
}

BATCH_STEP_FIELDS = {
    "Step 1": "inoculation",
    "Step 2": "culture_ph",
    "Step 3": "harvest",
    "Step 4": "purification",
}


def _batch_table_map(section):
    if section is None:
        return BATCH_HEADER_FIELDS
    if section.startswith("Batch summary"):
        return BATCH_SUMMARY_FIELDS
    if section.startswith("Label specimen"):
        return BATCH_LABEL_FIELDS
    return {}


def parse_batch(md_text):
    blocks = []
    md_buf = []
    page_refs = []
    section = None        # current ## section title
    section_lines = []    # body lines of a step section

    def flush_md():
        if md_buf:
            blocks.append(("md", "\n".join(md_buf)))
            md_buf.clear()

    def is_step(title):
        return title is not None and (
            title.startswith("Step 5")
            or any(title.startswith(p) for p in BATCH_STEP_FIELDS))

    def flush_section():
        nonlocal section_lines
        if not is_step(section):
            section_lines = []
            return
        title = section
        body = [ln.strip() for ln in section_lines if ln.strip()]
        section_lines = []
        if title.startswith("Step 5"):
            other = []
            for ln in body:
                if ln.startswith("Final protein concentration"):
                    blocks.append(
                        ("entry", "final_concentration",
                         f"Step 5 — {ln}"))
                elif ln.startswith("Independent verification"):
                    blocks.append(
                        ("entry", "filtration_verification",
                         f"Step 5 — {ln}"))
                else:
                    other.append(ln)
            if other:
                blocks.append(("md", "**Step 5 — also recorded:** "
                                 + "; ".join(other)))
            return
        step_key = next(
            key for prefix, key in BATCH_STEP_FIELDS.items()
            if title.startswith(prefix))
        text = "; ".join(
            ln[len("Entry: "):] if ln.startswith("Entry: ") else ln
            for ln in body)
        blocks.append(("entry", step_key,
                       f"{title} — {text if text else '(blank)'}"))

    for line in md_text.splitlines():
        stripped = line.strip()
        page_match = re.search(r"Page \d+ of \d+", stripped)
        if stripped.startswith("*Batch") and page_match:
            page_refs.append(page_match.group(0))
            continue
        if stripped.startswith("## "):
            flush_section()
            flush_md()
            section = stripped[3:].strip()
            if not is_step(section):
                md_buf.append(line)
            continue
        if is_step(section):
            section_lines.append(line)
            continue
        if stripped.startswith("|"):
            cells = _table_cells(stripped)
            table_map = _batch_table_map(section)
            if len(cells) >= 2 and cells[0] in table_map:
                flush_md()
                entry = cells[1] if cells[1] else "(blank)"
                blocks.append(
                    ("entry", table_map[cells[0]],
                     f"{cells[0]} — {entry}"))
                continue
            if _is_table_chrome(cells):
                continue
            if len(cells) >= 2:
                md_buf.append(f"**{cells[0]}:** {cells[1]}")
            continue
        md_buf.append(line)
    flush_section()
    flush_md()
    if page_refs:
        blocks.append(
            ("entry", "page_sequence",
             "Page sequence — " + " · ".join(page_refs)))
    return blocks


def with_absent_entries(blocks, fields):
    """Fields with no rendered entry (e.g. a step missing from the
    record entirely) get an explicit 'not present' entry at the end —
    noticing an absence is part of the review."""
    rendered = {b[1] for b in blocks if b[0] == "entry"}
    absent = [(key, label) for key, label in fields if key not in rendered]
    if absent:
        blocks.append(("md", "---\n**Not present in this record:**"))
        for key, label in absent:
            blocks.append(("entry", key, f"{label} — (not present)"))
    return blocks


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

st.title("QA Review Simulator — Fictitious Labs Inc.")
st.caption(
    "Review the completed record against the raw data and the governing "
    "documents in the Fictitious Labs EDMS. Click an entry to circle it "
    "as a discrepancy. You start with 10 points: every discrepancy you "
    "miss costs its share, and circling an entry that holds no "
    f"discrepancy costs {FP_PENALTY:g} points — a stray circle is cheap, "
    "spraying the page is not. You are not told how many discrepancies "
    "exist — real records don't say either."
)

scenario_ids = list_scenarios()
if not scenario_ids:
    st.error(
        "No scenarios found. Generate one with generator.py "
        "(it writes to the scenarios/ folder next to this app)."
    )
    st.stop()

scenario_id = st.selectbox("Scenario", scenario_ids)
main_md, second_md, ground_truth, family = load_scenario(scenario_id)
faults = ground_truth["faults"]

if family == "batch_record":
    ACTIVE_FIELDS = batch_gen.FIELDS
    ACTIVE_LABELS = batch_gen.FIELD_LABELS
    ACTIVE_CATEGORIES = batch_gen.CATEGORIES
    ACTIVE_REFERENCES = BATCH_REFERENCES
    main_title = "Batch record (record under review)"
    second_title = "Issuance record"
    blocks = parse_batch(main_md)
else:
    ACTIVE_FIELDS = FIELDS
    ACTIVE_LABELS = FIELD_LABELS
    ACTIVE_CATEGORIES = CATEGORIES
    ACTIVE_REFERENCES = REFERENCES
    main_title = "Worksheet (record under review)"
    second_title = "Raw data sheet"
    blocks = parse_a280(main_md)
blocks = with_absent_entries(blocks, ACTIVE_FIELDS)

# --- The record under review: click to circle ---
st.subheader(main_title)
circled_key = f"circled_{scenario_id}"
if circled_key not in st.session_state:
    st.session_state[circled_key] = set()
circled = st.session_state[circled_key]

for block in blocks:
    if block[0] == "md":
        st.markdown(block[1])
    else:
        _, field_key, display = block
        is_circled = field_key in circled
        label = ("⭕ " if is_circled else "○ ") + display
        if st.button(
            label,
            key=f"circle_{scenario_id}_{field_key}",
            type="primary" if is_circled else "secondary",
            use_container_width=True,
        ):
            if is_circled:
                circled.discard(field_key)
            else:
                circled.add(field_key)
            st.session_state.pop(f"result_{scenario_id}", None)
            st.rerun()

# --- The comparison document and the governing references ---
col_second, col_refs = st.columns(2)
with col_second:
    st.subheader(second_title)
    st.markdown(second_md)
with col_refs:
    st.subheader("Governing references")
    st.markdown(
        "Full texts live in the "
        f"[**Fictitious Labs EDMS**]({EDMS_URL}) — open it alongside "
        "this app. Finding the governing document is part of the job."
    )
    for number, title, version in ACTIVE_REFERENCES:
        st.markdown(f"- **{number}** — {title} ({version})")

# --- Submit ---
st.subheader("Your review")
st.markdown(
    f"**{len(circled)} "
    f"{'entry' if len(circled) == 1 else 'entries'} circled.** "
    "Submit when your review is complete."
)
submitted_key = f"result_{scenario_id}"
c_submit, c_clear = st.columns([1, 1])
with c_submit:
    if st.button("Submit review", key=f"submit_{scenario_id}",
                 type="primary"):
        st.session_state[submitted_key] = {
            "circled": sorted(circled),
            "result": score_circles(sorted(circled), faults),
        }
with c_clear:
    if st.button("Clear circles", key=f"clear_{scenario_id}"):
        circled.clear()
        st.session_state.pop(submitted_key, None)
        st.rerun()

# --- Score screen ---
if submitted_key in st.session_state:
    outcome = st.session_state[submitted_key]
    result = outcome["result"]
    counts = result["counts"]

    st.divider()
    st.subheader("Review outcome")
    m0, m1, m2, m3 = st.columns(4)
    m0.metric("Score", f"{result['points']:g} / 10")
    m1.metric("Caught", counts["caught"])
    m2.metric("Missed", counts["missed"])
    m3.metric("False positives", counts["false_positives"])

    def _fault_line(fault):
        difficulty = fault.get("difficulty")
        tag = f" ({difficulty})" if difficulty else ""
        return (
            f"- **{ACTIVE_LABELS[fault['field']]}** — "
            f"{ACTIVE_CATEGORIES[fault['fault_type']]}{tag}: "
            f"{fault['detail']}"
        )

    if result["caught"]:
        st.markdown("**Caught**")
        for fault in result["caught"]:
            st.markdown(_fault_line(fault))
    if result["missed"]:
        st.markdown("**Missed**")
        for fault in result["missed"]:
            st.markdown(_fault_line(fault))
    if result["false_positives"]:
        st.markdown(
            "**False positives** (circled, but no discrepancy there)")
        for flag in result["false_positives"]:
            st.markdown(f"- **{ACTIVE_LABELS[flag['field']]}**")
    if not faults and not result["false_positives"]:
        st.markdown(
            "This record was clean, and you circled nothing. "
            "A clean negative is a real answer.")
