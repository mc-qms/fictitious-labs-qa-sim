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
import sys

import streamlit.components.v1 as components

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from generator import FIELDS, FIELD_LABELS, CATEGORIES  # noqa: E402
import batch_generator as batch_gen  # noqa: E402
from scorer import score_circles, FP_PENALTY  # noqa: E402
from docparse import (  # noqa: E402
    parse_a280, parse_batch, parse_generic,
    with_absent_entries, build_doc_html,
)

# The record renderer: a custom component that draws the record as a
# paper form and lets the reviewer circle entries with a red pen.
_circle_doc = components.declare_component(
    "circle_doc", path=os.path.join(BASE, "components", "circle_doc"))

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
# App
# ------------------------------------------------------------------

st.title("QA Review Simulator — Fictitious Labs Inc.")
st.caption(
    "Review the completed record against the source document and the "
    "governing documents in the Fictitious Labs EDMS. Click an entry "
    "on the record to circle it as a discrepancy — click again to "
    "uncircle. You start with 10 points: every discrepancy you miss "
    "costs its share, and circling an entry that holds no discrepancy "
    f"costs {FP_PENALTY:g} points — a stray circle is cheap, spraying "
    "the page is not. You are not told how many discrepancies exist — "
    "real records don't say either."
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
    blocks = parse_a280(main_md, FIELDS)
blocks = with_absent_entries(blocks, ACTIVE_FIELDS)
second_blocks = parse_generic(second_md)

# --- The record under review: a paper form, click to circle ---
st.subheader(main_title)
circled_key = f"circled_{scenario_id}"
if circled_key not in st.session_state:
    st.session_state[circled_key] = []
gen_key = f"docgen_{scenario_id}"
if gen_key not in st.session_state:
    st.session_state[gen_key] = 0
submitted_key = f"result_{scenario_id}"

returned = _circle_doc(
    html=build_doc_html(blocks),
    initial=st.session_state[circled_key],
    interactive=True,
    key=f"doc_{scenario_id}_{st.session_state[gen_key]}",
    default=st.session_state[circled_key],
)
if returned is not None:
    new_circled = sorted(set(returned))
    if new_circled != st.session_state[circled_key]:
        st.session_state[circled_key] = new_circled
        stored = st.session_state.get(submitted_key)
        if stored and stored["circled"] != new_circled:
            st.session_state.pop(submitted_key, None)
circled = st.session_state[circled_key]

# --- The comparison document and the governing references ---
col_second, col_refs = st.columns(2)
with col_second:
    st.subheader(second_title)
    _circle_doc(
        html=build_doc_html(second_blocks),
        initial=[],
        interactive=False,
        key=f"ref_{scenario_id}",
        default=None,
    )
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
c_submit, c_clear = st.columns([1, 1])
with c_submit:
    if st.button("Submit review", key=f"submit_{scenario_id}",
                 type="primary"):
        st.session_state[submitted_key] = {
            "circled": list(circled),
            "result": score_circles(list(circled), faults),
        }
with c_clear:
    if st.button("Clear circles", key=f"clear_{scenario_id}"):
        st.session_state[circled_key] = []
        st.session_state[gen_key] += 1
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
