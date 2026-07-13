#!/usr/bin/env python3
"""运行 Stage B1 预注册网格研究并写出权威 JSONL。"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.free_time_search import search_mesh
from experiments.physical_model import (
    PhysicalModelConfig, audit_fixed_time_result, classify_audit_metrics,
    solve_fixed_time,
)
from experiments.study_contracts import load_study_manifest


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _solve(N, tf, solver, audit_tolerances):
    config = PhysicalModelConfig(N=N, tf_s=float(tf))
    result = solve_fixed_time(config, solver)
    payload = {
        "solver": solver, "solver_status": result.solver_status,
        "classification": result.classification, "fuel_kg": result.fuel_kg,
        "terminal_mass_kg": result.terminal_mass_kg,
        "objective_value": result.objective_value, "num_iters": result.num_iters,
        "metrics": {}, "error_type": "none", "error": result.error,
    }
    if result.classification == "success":
        metrics = audit_fixed_time_result(config, result)
        payload["metrics"] = metrics
        payload["classification"] = classify_audit_metrics(
            result.classification, metrics, audit_tolerances
        )
    if payload["classification"] == "solver_error":
        payload["error_type"] = result.error.split(":", 1)[0] or "solver_error"
    return payload


def _run_mesh(args):
    N, search, tolerances = args
    callback = lambda mesh, tf: _solve(mesh, tf, "ECOS", tolerances)
    return search_mesh(
        N, search["lower_s"], search["upper_s"],
        [level["step_s"] for level in search["levels"]], callback,
    )


def run_study(manifest_path, output_path, workers=4):
    manifest = load_study_manifest(manifest_path)
    jobs = [(N, manifest["terminal_time_search"], manifest["tolerances"]["audit"])
            for N in manifest["meshes"]]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        groups = list(executor.map(_run_mesh, jobs))
    records = [record for group in groups for record in group]
    for N in manifest["meshes"]:
        candidates = [r for r in records if r["N"] == N and r["classification"] == "success"]
        if candidates:
            best = min(candidates, key=lambda r: r["fuel_kg"])
            tf = Decimal(best["tf_s"])
            payload = _solve(N, tf, "Clarabel", manifest["tolerances"]["audit"])
            confirmation = {
                "candidate_id": best["candidate_id"] + "_clarabel", "N": N,
                "tf_s": best["tf_s"], "search_level": "confirmation", **payload,
            }
            records.append(confirmation)
    manifest_sha = _digest(manifest_path)
    records.sort(key=lambda r: (r["N"], Decimal(r["tf_s"]), r["solver"]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for index, record in enumerate(records):
            record.update({
                "schema_version": 1, "study_id": manifest["study_id"],
                "model_id": manifest["model_id"], "record_id": index,
                "manifest_sha256": manifest_sha,
            })
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="experiments/studies/free_time_mesh_v1.json")
    parser.add_argument("--output", default="experiments/results/free_time_mesh_v1.jsonl")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    records = run_study(args.manifest, args.output, args.workers)
    print(f"wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
