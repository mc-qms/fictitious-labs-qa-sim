"""Deal a fresh record for the QA Review Simulator.

Every record the app shows is generated at the moment it is dealt:
a random seed and a random set of planted faults, possibly none.
There is no fixed scenario list, so nothing about a record is
given away before the review — a clean record is always possible,
and telling one from a faulty record is the review itself.

The generators are correct-by-construction (generator.py,
batch_generator.py): the record is built right, then the sampled
faults are applied from the family's registered fault list, so
the answer key is known exactly.

Two difficulties. Easy deals only Easy-tagged faults — minor
GDP errors — and never many (0-3). Hard deals from the family's
full fault list across a wider count range (0-6): clean records
still come up, and a tail of heavy records (5-6 faults) comes
up about one deal in seven. Either way a clean record is always
possible, so finding nothing remains a real answer.
"""

import generator as a280_gen
import batch_generator as batch_gen

# Weights for fault counts, per mode, indexed by the count.
_COUNT_WEIGHTS = {
    "easy": [2, 3, 2, 1],
    "hard": [2, 3, 3, 3, 2, 1, 1],
}

_FAMILIES = {
    "a280": (a280_gen.build_scenario, a280_gen.FAULT_TYPES,
             a280_gen.DIFFICULTY),
    "batch_record": (batch_gen.build_scenario, batch_gen.FAULT_TYPES,
                     batch_gen.DIFFICULTY),
}


def deal(rng, family, mode="hard"):
    """Deal one record. `rng` is a random.Random-like object.

    Returns (main_md, second_md, ground_truth, family): the record
    under review, the document it is checked against, and the
    ground truth whose "faults" list is the answer key.
    """
    build, fault_types, difficulty = _FAMILIES[family]
    if mode == "easy":
        pool = [f for f in fault_types if difficulty[f] == "easy"]
    else:
        pool = list(fault_types)
    weights = _COUNT_WEIGHTS[mode]
    count = rng.choices(range(len(weights)), weights=weights)[0]
    count = min(count, len(pool))
    attempts = 0
    while True:
        attempts += 1
        seed = rng.randrange(1, 2 ** 31)
        faults = rng.sample(pool, count) if count else []
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
