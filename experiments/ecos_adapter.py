"""CVXPY+ECOS 求解器到逐样本结果合同的适配器。"""

import platform
import subprocess
import sys
import time
from pathlib import Path

import cvxpy as cp
import ecos
import numpy as np

from experiments.solution_audit import classify_metrics, compute_metrics


def _git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _provenance(digest):
    return {
        "manifest_sha256": digest,
        "platform": f"{platform.system()}-{platform.machine()}",
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "cvxpy_version": cp.__version__,
        "ecos_version": getattr(ecos, "__version__", "unknown"),
        "git_commit": _git_commit(),
    }


def solve_sample(sample, scenario, digest):
    """求解一个样本；任何求解失败也生成可验证记录。"""
    mars_dir = Path(__file__).resolve().parents[1] / "MarsLanding"
    if str(mars_dir) not in sys.path:
        sys.path.insert(0, str(mars_dir))
    import mars_solve

    status = "solver_error"
    metrics = {"elapsed_ns": 0, "ecos_iterations": 0}
    classification = "solver_error"
    error_type = "Exception"
    started = time.perf_counter_ns()
    try:
        fuel, solution = mars_solve.solve_cvxpy(
            cp.ECOS, return_full=True,
            initial_r0=np.asarray(sample["r0_m"], dtype=float),
            initial_v0=np.asarray(sample["v0_mps"], dtype=float),
        )
        status = solution["solver_status"]
        metrics.update(compute_metrics(solution))
        metrics["fuel_kg"] = float(fuel)
        metrics["ecos_iterations"] = solution["num_iters"]
        classification = classify_metrics(status, {
            name: metrics[name] for name in (
                "terminal_position_m", "terminal_velocity_mps",
                "max_dynamics_residual", "max_cone_violation",
                "mass_bound_violation_kg",
            )
        }, scenario["tolerances"])
        error_type = "none"
    except mars_solve.CvxpySolveError as error:
        status = str(error.status or "solver_error")
        classification = classify_metrics(status, {}, scenario["tolerances"])
        error_type = "none" if classification != "solver_error" else "CvxpySolveError"
    except Exception:
        status = "exception"
        classification = "solver_error"
        error_type = "Exception"
    finally:
        metrics["elapsed_ns"] = time.perf_counter_ns() - started

    return {
        "schema_version": 1, "scenario_id": scenario["scenario_id"],
        "sample_id": sample["sample_id"],
        "input": {"r0_m": sample["r0_m"], "v0_mps": sample["v0_mps"]},
        "solver": scenario["solver"], "solver_status": status,
        "classification": classification, "success": classification == "success",
        "error_type": error_type,
        "metrics": metrics, "provenance": _provenance(digest),
    }
