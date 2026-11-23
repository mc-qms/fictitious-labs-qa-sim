"""Fictitious Labs QA Simulator — record parsing and paper HTML.

Pure functions, stdlib only. Parses a generated record (markdown)
into structured blocks, and renders the blocks as the paper-form
HTML the circle_doc component draws.

Block model:
  {"kind": "title"|"section"|"para", "text": str}
  {"kind": "row", "label": str, "value": str,
   "field": field key or None, "absent": bool}

Every row of the record is one circleable entry. A row whose
label maps to a record field carries that field key; any other
row carries a ctx_ key, so the whole form is clickable - the
reviewer can circle anything on the page, and entries that are
not record fields simply never hold a planted fault. Every field
of the record appears as exactly one row; a field whose entry is
missing from the record entirely gets an explicit "not present"
row (with_absent_entries).
"""

import html as html_lib
import re

# Batch-record table-row label -> field key, by table context. The
# batch summary repeats the batch number and the label table repeats
# the retest date, so the maps are context-specific: each field gets
# exactly one circleable row in the whole record.
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


def _row(label, value, field=None, absent=False):
    return {"kind": "row", "label": label,
            "value": value if value else "(blank)",
            "field": field, "absent": absent}


def _ctx_key(label, used):
    """A unique context-entry key for a row that is not a record
    field: ctx_ + the slugged label, numbered on collision."""
    base = "ctx_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    key = base
    n = 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def parse_a280(md_text, fields):
    label_to_key = {label: key for key, label in fields}
    used = set()
    blocks = []
    for line in md_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            blocks.append({"kind": "title", "text": stripped[2:]})
        elif stripped.startswith("|"):
            cells = _table_cells(stripped)
            if _is_table_chrome(cells):
                continue
            if len(cells) >= 2:
                field = label_to_key.get(cells[0])
                if field is None:
                    field = _ctx_key(cells[0], used)
                blocks.append(_row(cells[0], cells[1], field))
        else:
            blocks.append({"kind": "para", "text": stripped})
    return blocks


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
    page_refs = []
    section = None
    section_lines = []
    used = set()

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
            blocks.append({"kind": "section", "text": title})
            for ln in body:
                if ln.startswith("Final protein concentration"):
                    label, _, value = ln.partition(": ")
                    blocks.append(_row(label, value, "final_concentration"))
                elif ln.startswith("Independent verification"):
                    label, _, value = ln.partition(": ")
                    blocks.append(
                        _row(label, value, "filtration_verification"))
                elif ln.startswith("Performed by "):
                    blocks.append(_row(
                        "Performed by", ln[len("Performed by "):],
                        _ctx_key("Performed by", used)))
                elif ": " in ln:
                    label, _, value = ln.partition(": ")
                    blocks.append(
                        _row(label, value, _ctx_key(label, used)))
                else:
                    blocks.append({"kind": "para", "text": ln})
            return
        step_key = next(
            key for prefix, key in BATCH_STEP_FIELDS.items()
            if title.startswith(prefix))
        text = "; ".join(
            ln[len("Entry: "):] if ln.startswith("Entry: ") else ln
            for ln in body)
        # The attribution ("performed by DA, 2026-11-10") is its
        # own entry, not part of the step's value: a reviewer
        # circles the value or the signature line, not both at
        # once. A blank step has no attribution to split off.
        matches = list(re.finditer(r";\s*[Pp]erformed by\s+", text))
        if matches:
            cut = matches[-1]
            blocks.append(_row(title, text[:cut.start()], step_key))
            blocks.append(_row(
                "Performed by", text[cut.end():],
                f"ctx_{step_key}_performed_by"))
        else:
            blocks.append(_row(title, text, step_key))

    for line in md_text.splitlines():
        stripped = line.strip()
        page_match = re.search(r"Page \d+ of \d+", stripped)
        if stripped.startswith("*Batch") and page_match:
            page_refs.append(page_match.group(0))
            continue
        if stripped.startswith("## "):
            flush_section()
            section = stripped[3:].strip()
            if not is_step(section):
                blocks.append({"kind": "section", "text": section})
            continue
        if stripped.startswith("# "):
            blocks.append({"kind": "title", "text": stripped[2:]})
            continue
        if is_step(section):
            section_lines.append(line)
            continue
        if not stripped:
            continue
        if stripped.startswith("|"):
            cells = _table_cells(stripped)
            if _is_table_chrome(cells):
                continue
            if len(cells) >= 2:
                table_map = _batch_table_map(section)
                field = table_map.get(cells[0])
                if field is None:
                    field = _ctx_key(cells[0], used)
                blocks.append(_row(cells[0], cells[1], field))
            continue
        blocks.append({"kind": "para", "text": stripped})
    flush_section()
    if page_refs:
        blocks.append(
            _row("Page sequence", " · ".join(page_refs), "page_sequence"))
    return blocks


def parse_generic(md_text):
    """Reference documents (raw data sheet, issuance record): same
    paper rendering, nothing circleable."""
    blocks = []
    for line in md_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            blocks.append({"kind": "title", "text": stripped[2:]})
        elif stripped.startswith("## "):
            blocks.append({"kind": "section", "text": stripped[3:]})
        elif stripped.startswith("|"):
            cells = _table_cells(stripped)
            if _is_table_chrome(cells):
                continue
            if len(cells) >= 2:
                blocks.append(_row(cells[0], cells[1]))
        else:
            blocks.append({"kind": "para", "text": stripped})
    return blocks


def with_absent_entries(blocks, fields):
    """Fields with no rendered row (e.g. a step missing from the
    record entirely) get an explicit 'not present' row at the end —
    noticing an absence is part of the review."""
    rendered = {b["field"] for b in blocks
                if b["kind"] == "row" and b.get("field")}
    absent = [(key, label) for key, label in fields if key not in rendered]
    if absent:
        blocks.append(
            {"kind": "section", "text": "Not present in this record"})
        for key, label in absent:
            blocks.append(_row(label, "(not present)", key, absent=True))
    return blocks


def _fmt(text):
    # The generators mark a blank entry as *(blank)* (markdown
    # italics); on paper it is just the words.
    text = text.replace("*(blank)*", "(blank)")
    escaped = html_lib.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def build_doc_html(blocks):
    parts = ['<div class="paper">']
    for b in blocks:
        if b["kind"] == "title":
            parts.append(f'<h1 class="doc-title">{_fmt(b["text"])}</h1>')
        elif b["kind"] == "section":
            parts.append(
                f'<h2 class="doc-section">{_fmt(b["text"])}</h2>')
        elif b["kind"] == "para":
            parts.append(f'<p class="para">{_fmt(b["text"])}</p>')
        elif b["kind"] == "row":
            cls = "row absent" if b.get("absent") else "row"
            field_attr = (f' data-field="{b["field"]}"'
                          if b.get("field") else "")
            parts.append(
                f'<div class="{cls}"{field_attr}>'
                f'<span class="lbl">{_fmt(b["label"])}</span>'
                f'<span class="val">{_fmt(b["value"])}</span></div>')
    parts.append("</div>")
    return "".join(parts)
