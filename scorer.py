"""Fictitious Labs QA Simulator — scorer.

Pure functions, no I/O. Two scoring modes:

- score(): the original flag mode. A flag catches a fault only when
  BOTH the field and the discrepancy category match the planted
  fault. A flag that matches no remaining fault — wrong field, wrong
  category, or a duplicate of an already-caught fault — is a false
  positive. Faults with no matching flag are missed.

- score_circles(): the click-to-circle mode used by the app. The
  reviewer circles entries on the record itself; only the location
  counts. Scoring starts at 10 points: each planted fault is worth
  an equal slice of the 10 (with 3 planted, about 3.3 points each),
  and each circled entry that holds no discrepancy costs FP_PENALTY
  points (a stray circle is cheap; spraying the page is not). The
  score never goes below 0.
"""

FP_PENALTY = 0.5


def score(flags, faults):
    """flags: [{"field": str, "category": fault_type}]
    faults: ground-truth list [{"field", "fault_type", "detail"}]
    Returns {"caught", "missed", "false_positives", "counts"}."""
    remaining = list(faults)
    caught = []
    false_positives = []
    for flag in flags:
        match = None
        for fault in remaining:
            if (fault["field"] == flag["field"]
                    and fault["fault_type"] == flag["category"]):
                match = fault
                break
        if match is not None:
            remaining.remove(match)
            caught.append(match)
        else:
            false_positives.append(flag)
    return {
        "caught": caught,
        "missed": remaining,
        "false_positives": false_positives,
        "counts": {
            "caught": len(caught),
            "missed": len(remaining),
            "false_positives": len(false_positives),
        },
    }


def score_circles(circled_fields, faults):
    """circled_fields: iterable of field keys the reviewer circled.
    faults: ground-truth list [{"field", "fault_type", "detail"}]
    Returns the score() shape plus "points" (0-10, one decimal)."""
    circled = list(dict.fromkeys(circled_fields))
    fault_fields = {fault["field"] for fault in faults}
    caught = [f for f in faults if f["field"] in circled]
    missed = [f for f in faults if f["field"] not in circled]
    false_positives = [
        {"field": key} for key in circled if key not in fault_fields
    ]
    if faults:
        points = len(caught) * (10.0 / len(faults))
    else:
        points = 10.0
    points = max(0.0, points - FP_PENALTY * len(false_positives))
    return {
        "caught": caught,
        "missed": missed,
        "false_positives": false_positives,
        "counts": {
            "caught": len(caught),
            "missed": len(missed),
            "false_positives": len(false_positives),
        },
        "points": round(points, 1),
    }
