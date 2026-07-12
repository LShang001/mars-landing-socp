"""不可变逐样本 Monte Carlo JSONL runner。"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from experiments.contracts import validate_result
from experiments.scenario_loader import load_scenario, sample_inputs


def _fsync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_experiment(manifest_path, output_path, count=None, solver=None):
    """执行清单并仅在全部尝试完成后原子发布结果。"""
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    if os.path.lexists(output_path):
        raise FileExistsError(f"output already exists: {output_path}")

    scenario, digest = load_scenario(manifest_path)
    samples = sample_inputs(scenario, count=count)
    if solver is None:
        from experiments.ecos_adapter import solve_sample
        solver = solve_sample

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for sample in samples:
                result = solver(sample, scenario, digest)
                validate_result(result)
                stream.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        try:
            os.link(temporary, output_path)
        except FileExistsError:
            raise FileExistsError(f"output already exists: {output_path}") from None
        temporary.unlink()
        _fsync_directory(output_path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int)
    args = parser.parse_args(argv)
    run_experiment(args.scenario, args.output, args.count)


if __name__ == "__main__":
    main()
