import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from experiments.contracts import validate_scenario


def load_scenario(path: Path):
    raw = path.read_bytes()
    def reject_constant(value):
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    scenario = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(scenario, Mapping):
        raise ValueError("scenario JSON root must be an object")
    validate_scenario(scenario)
    return scenario, hashlib.sha256(raw).hexdigest()


def sample_inputs(scenario, count=None):
    count = scenario["sample_count"] if count is None else count
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("count must be a positive integer within the manifest sample_count")
    if count < 1 or count > scenario["sample_count"]:
        raise ValueError("count must be within the manifest sample_count")
    rng = np.random.RandomState(scenario["seed"])
    samples = []
    for sample_id in range(count):
        item = {"sample_id": sample_id}
        for name in ("r0_m", "v0_mps"):
            nominal = np.asarray(scenario["nominal"][name], dtype=float)
            width = np.asarray(scenario["perturbations"][name]["half_width"], dtype=float)
            item[name] = (nominal + rng.uniform(-width, width)).tolist()
        samples.append(item)
    return samples
