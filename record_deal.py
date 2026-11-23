"""Deal a fresh record for the QA Review Simulator.

Every record the app shows is generated at the moment it is dealt:
a random seed and a random set of planted faults, possibly none.
There is no fixed scenario list, so nothing about a record is
given away before the review — a clean record is always possible,
and telling one from a faulty record is the review itself.

The generators are correct-by-construction (generator.py,
batch_generator.py): the record is built right, then the sampled
faults are applied from the family's registered fault list, so
the answer key is known exactly. Fault counts run 0-4, weighted
so a clean record comes up roughly one deal in five — common
enough to keep a reviewer honest, not so common that finding
faults feels like the trick.
"""

import generator as a280_gen
import batch_generator as batch_gen

# Weights for fault counts 0, 1, 2, 3, 4.
_COUNT_WEIGHTS = [2, 3, 3, 2, 1]

_FAMILIES = {
    "a280": (a280_gen.build_scenario, a280_gen.FAULT_TYPES),
    "batch_record": (batch_gen.build_scenario, batch_gen.FAULT_TYPES),
}


def deal(rng, family):
    """Deal one record. `rng` is a random.Random-like object.

    Returns (main_md, second_md, ground_truth, family): the record
    under review, the document it is checked against, and the
    ground truth whose "faults" list is the answer key.
    """
    build, fault_types = _FAMILIES[family]
    count = rng.choices(range(len(_COUNT_WEIGHTS)),
                        weights=_COUNT_WEIGHTS)[0]
    attempts = 0
    while True:
        attempts += 1
        seed = rng.randrange(1, 2 ** 31)
        faults = rng.sample(fault_types, count) if count else []
        try:
            scenario = build(seed, faults, f"live-{seed}")
        except ValueError:
            # A sampled combination the generator refuses (the
            # batch family has incompatible fault pairs): resample.
            scenario = None
        if scenario is not None:
            fields = [f["field"]
                      for f in scenario["ground_truth"]["faults"]]
            if len(fields) == len(set(fields)):
                break
        if attempts >= 30:
            # Still nothing coherent: step the count down, and
            # bottom out at a clean record, which always builds.
            if count > 0:
                count -= 1
                attempts = 0
            else:
                scenario = build(seed, [], f"live-{seed}")
                break
    ground_truth = scenario["ground_truth"]
    if family == "batch_record":
        return (scenario["record_md"], scenario["issuance_md"],
                ground_truth, family)
    return (scenario["worksheet_md"], scenario["raw_md"],
            ground_truth, family)
