#!/usr/bin/env python3
"""从 Stage B1 JSONL 重算网格最优与跨求解器差异。"""

import argparse
import hashlib
import json
from pathlib import Path


def aggregate(raw_path):
    raw = Path(raw_path)
    records = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    meshes = sorted({record["N"] for record in records})
    per_mesh = []
    for N in meshes:
        group = [r for r in records if r["N"] == N]
        ecos = [r for r in group if r["solver"] == "ECOS" and r["classification"] == "success"]
        best = min(ecos, key=lambda r: r["fuel_kg"]) if ecos else None
        confirmation = next((r for r in group if r["solver"] == "Clarabel"
                             and best and r["tf_s"] == best["tf_s"]), None)
        counts = {}
        for record in group:
            counts[record["classification"]] = counts.get(record["classification"], 0) + 1
        per_mesh.append({
            "N": N, "attempts": len(group), "classification_counts": counts,
            "best_ecos": best,
            "clarabel_confirmation": confirmation,
            "cross_solver_fuel_delta_kg": (
                abs(best["fuel_kg"] - confirmation["fuel_kg"])
                if best and confirmation and confirmation["classification"] == "success" else None
            ),
        })
    return {
        "schema_version": 1, "study_id": records[0]["study_id"],
        "model_id": records[0]["model_id"], "record_count": len(records),
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "per_mesh": per_mesh,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw")
    parser.add_argument("summary")
    args = parser.parse_args()
    summary = aggregate(args.raw)
    Path(args.summary).write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.summary}")


if __name__ == "__main__":
    main()
