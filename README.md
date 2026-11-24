# QA Review Simulator — Fictitious Labs Inc.

A training game for the most common QA skill nobody practices on
purpose: **reviewing a completed record and catching what's wrong
with it.**

You are shown a finished record — an executed batch record or a
completed QC assay worksheet — together with the source document it
must agree with (an FL-EDMS issuance record, a raw data sheet) and a
list of the governing documents, which live in the companion
[Fictitious Labs EDMS](https://fictitious-labs-edms.streamlit.app/).
Click any entry on the record to circle it as a discrepancy, then
submit your review.

**Scoring.** You start with 10 points. Each planted discrepancy is
worth an equal slice of the 10 points — with 3 planted, each is
worth about 3.3 points, and missing one drops your score by that
much. Circling
an entry that holds no discrepancy costs half a point — a stray
circle is cheap; spraying the page is not. Scoring is exact and
deterministic: the same circles on the same record always produce
the same score.

**Scope.** Discrepancies are documentation and transcription errors
only — a value that doesn't match its source, a superseded template,
a missing verification, a label that disagrees with the record.
Nobody is asked to check arithmetic; that's peer review, not record
review. Some records are clean — no discrepancy at all. A clean record
reviewed cleanly is a perfect score.

## Record families

- **A280 assay worksheet** (FRM-QC-101) — a completed protein
  concentration worksheet checked against its raw data sheet,
  TM-QC-101, and the GDP and numerical-reporting SOPs.
- **Executed batch record** (FRM-MF-101) — a six-page batch record
  checked against its master batch record (current and superseded
  versions), its issuance record, and the packaging instructions.

## Difficulty

- **Easy** — minor GDP errors, if any. A few surface slips at
  most, every one visible on the record itself.
- **Hard** — may require referencing the EDMS. The full fault
  range, from clean records to rare heavy ones, including faults
  only catchable against the governing documents.

Records are generated fresh for every review: correct-by-
construction from templates, with a random set of faults applied
from a registered fault list — possibly none — so the answer key
is known exactly and no two visits need see the same record.

## Running locally

```
pip install -r requirements.txt
streamlit run app.py
```

## About

Part of the Fictitious Labs showcase: a complete fictional biologics
quality system — 42 controlled documents in a working EDMS, produced
with the Procedure Machine — built to demonstrate governed AI in
regulated quality work. Fictitious Labs Inc. is not a real company;
FL-101 is not a real product; no real records are used.

- EDMS: https://fictitious-labs-edms.streamlit.app/
- Showcase: https://mc-qms.github.io
