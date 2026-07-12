"""Aggregate Monte Carlo result JSONL into a deterministic summary."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path

from experiments.contracts import ContractError, validate_result


WILSON_Z_95 = 1.959963984540054


def _wilson_interval(successes, attempts):
    rate = successes / attempts
    z2 = WILSON_Z_95**2
    denominator = 1.0 + z2 / attempts
    center = (rate + z2 / (2.0 * attempts)) / denominator
    margin = (WILSON_Z_95 / denominator) * math.sqrt(
        rate * (1.0 - rate) / attempts + z2 / (4.0 * attempts**2))
    return {"lower": center - margin, "upper": center + margin}


class Accumulator:
    """Online result statistics using Welford's stable variance algorithm."""

    def __init__(self):
        self.attempted = 0
        self.classifications = Counter()
        self.fuel_count = 0
        self.fuel_mean = 0.0
        self.fuel_m2 = 0.0
        self.fuel_min = None
        self.fuel_max = None

    def add(self, record):
        validate_result(record)
        self.attempted += 1
        self.classifications[record["classification"]] += 1
        if record["success"]:
            if "fuel_kg" not in record["metrics"]:
                raise ValueError("successful result must contain metrics.fuel_kg")
            fuel = record["metrics"]["fuel_kg"]
            self.fuel_count += 1
            delta = fuel - self.fuel_mean
            self.fuel_mean += delta / self.fuel_count
            self.fuel_m2 += delta * (fuel - self.fuel_mean)
            self.fuel_min = fuel if self.fuel_min is None else min(self.fuel_min, fuel)
            self.fuel_max = fuel if self.fuel_max is None else max(self.fuel_max, fuel)

    def summary(self):
        if not self.attempted:
            raise ValueError("cannot aggregate empty results")
        successful = self.classifications.get("success", 0)
        return {
            "attempted": self.attempted,
            "successful": successful,
            "classification_counts": dict(sorted(self.classifications.items())),
            "success_rate": successful / self.attempted,
            "success_rate_wilson_95": _wilson_interval(successful, self.attempted),
            "fuel_kg": {
                "count": self.fuel_count,
                "mean": self.fuel_mean if self.fuel_count else None,
                "sample_std": (math.sqrt(self.fuel_m2 / (self.fuel_count - 1))
                               if self.fuel_count > 1 else
                               (0.0 if self.fuel_count else None)),
                "min": self.fuel_min,
                "max": self.fuel_max,
            },
        }


def aggregate(records):
    """Validate and summarize a non-empty iterable of result records."""
    accumulator = Accumulator()
    for record in records:
        accumulator.add(record)
    return accumulator.summary()


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def _atomic_write_new(path, data):
    if os.path.lexists(path):
        raise FileExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input JSONL results")
    parser.add_argument("output", type=Path, help="new summary JSON path")
    args = parser.parse_args(argv)
    try:
        accumulator = Accumulator()
        input_hash = hashlib.sha256()
        seen = set()
        scenario_id = None
        digest = None
        with args.input.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                input_hash.update(raw_line)
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError(f"invalid UTF-8 at line {line_number}: {error}") from error
                if not line.strip():
                    raise ValueError(f"blank JSONL line at line {line_number}")
                try:
                    record = json.loads(line, parse_constant=_reject_constant)
                except (json.JSONDecodeError, ValueError) as error:
                    raise ValueError(f"invalid JSON at line {line_number}: {error}") from error
                try:
                    accumulator.add(record)
                except (ContractError, ValueError) as error:
                    raise ValueError(f"invalid result at line {line_number}: {error}") from error
                sample_id = record["sample_id"]
                if sample_id in seen:
                    raise ValueError(f"duplicate sample_id: {sample_id}")
                seen.add(sample_id)
                current_scenario = record["scenario_id"]
                current_digest = record["provenance"]["manifest_sha256"].lower()
                if scenario_id is not None and current_scenario != scenario_id:
                    raise ValueError("mixed scenario_id values")
                if digest is not None and current_digest != digest:
                    raise ValueError("mixed manifest_sha256 values")
                scenario_id, digest = current_scenario, current_digest
        summary = accumulator.summary()
        summary.update({
            "scenario_id": scenario_id,
            "manifest_sha256": digest,
            "input_sha256": input_hash.hexdigest(),
        })
        encoded = (json.dumps(summary, sort_keys=True, indent=2, allow_nan=False)
                   + "\n").encode("utf-8")
        _atomic_write_new(args.output, encoded)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
