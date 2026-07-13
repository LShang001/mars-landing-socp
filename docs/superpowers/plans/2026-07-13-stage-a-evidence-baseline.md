# Stage A Evidence Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned, testable experiment and evidence pipeline so every robustness, timing, and manuscript claim is reproducible while preserving `MarsLanding/MarsLanding.c` as the original independent handwritten sparse-matrix implementation.

**Architecture:** A JSON scenario manifest defines deterministic samples; a solver adapter produces one JSONL record per attempted sample; independent audit and aggregation modules classify physical/numerical outcomes and calculate statistics. Benchmark records and manuscript claims use the same provenance envelope. CI runs contract tests and small deterministic smoke experiments, while confirmation datasets remain explicit release artifacts.

**Tech Stack:** Python 3 standard library, NumPy, CVXPY/ECOS, JSON/JSONL, `unittest`, Bash CI, existing CMake/ECOS targets, XeLaTeX.

---

## File Structure

- Create `experiments/__init__.py`: package marker.
- Create `experiments/contracts.py`: scenario, result, provenance, and validation contracts.
- Create `experiments/scenarios/near_nominal_v1.json`: canonical near-nominal Monte Carlo definition.
- Create `experiments/scenario_loader.py`: deterministic sample generation and manifest hashing.
- Create `experiments/solution_audit.py`: terminal, dynamics, cone, and mass-bound residual checks.
- Create `experiments/ecos_adapter.py`: CVXPY+ECOS execution producing contract records.
- Create `experiments/run_monte_carlo.py`: immutable JSONL experiment runner.
- Create `experiments/aggregate_results.py`: Wilson interval, failure taxonomy, and summary JSON.
- Create `experiments/benchmark_host.py`: staged host benchmark record generator.
- Create `experiments/benchmark_protocol.json`: measurement conditions and required statistics.
- Create `paper/evidence/claims.json`: manuscript claim-to-evidence ledger.
- Create `paper/evidence/check_claims.py`: ledger and manuscript consistency checker.
- Create `research/literature/review_protocol.md`: repeatable literature search and screening protocol.
- Create `research/literature/literature_matrix.csv`: source-level method, evidence, and gap matrix.
- Create `research/literature/check_literature.py`: DOI, required-field, and manuscript-citation checks.
- Create `docs/provenance/handwritten-matrix.md`: provenance and non-replacement policy.
- Create `tests/`: standard-library unit and integration tests for all contracts.
- Modify `MarsLanding/mars_robustness.py`: compatibility wrapper around the new experiment pipeline.
- Modify `MarsLanding/check_model_consistency.py`: handwritten-target protection checks.
- Modify `ci/validate.sh`: contract, provenance, and deterministic smoke gates.
- Modify `paper/chapters/ch5_results.tex`: replace unreproducible Monte Carlo numbers with generated evidence.
- Modify `README.md` and `AGENTS.md`: document experiment entry points and mandatory provenance rules.

## Task 0: Establish Systematic Literature Research

**Files:**
- Create: `research/literature/review_protocol.md`
- Create: `research/literature/literature_matrix.csv`
- Create: `research/literature/check_literature.py`
- Test: `tests/test_literature_matrix.py`
- Modify: `paper/refs.bib`

- [x] **Step 1: Write failing literature-matrix tests**

```python
# tests/test_literature_matrix.py
import unittest

from research.literature.check_literature import validate_rows


class LiteratureMatrixTests(unittest.TestCase):
    def test_peer_reviewed_source_requires_traceable_identity(self):
        rows = [{"source_id": "blackmore2010minimum", "year": "2010",
                 "venue": "Journal of Guidance, Control, and Dynamics",
                 "doi": "10.2514/1.47202", "url": "",
                 "theme": "lossless_convexification", "method": "SOCP",
                 "problem": "powered descent", "hardware": "not reported",
                 "evidence": "simulation", "relevance": "baseline theory",
                 "gap": "no embedded timing", "verification": "publisher metadata checked"}]
        self.assertEqual(validate_rows(rows), [])

    def test_missing_method_and_verification_are_rejected(self):
        rows = [{"source_id": "x", "year": "2025", "venue": "unknown",
                 "doi": "", "url": "", "theme": "embedded_optimization",
                 "method": "", "problem": "powered descent", "hardware": "",
                 "evidence": "", "relevance": "", "gap": "",
                 "verification": ""}]
        failures = validate_rows(rows)
        self.assertTrue(any("method" in failure for failure in failures))
        self.assertTrue(any("verification" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test and confirm the missing research package**

Run: `python3 -m unittest tests.test_literature_matrix -v`

Expected: import failure for `research.literature.check_literature`.

- [x] **Step 3: Implement the protocol and validator**

The protocol must record the search date, databases, exact query strings, year window, inclusion/exclusion rules, backward/forward citation procedure, duplicate handling, and update cadence. Search at least these themes independently: lossless convexification for powered descent; successive/ sequential convex programming for guidance; warm-start and factorization reuse in conic optimization; embedded real-time convex optimization; robust/chance-constrained powered descent; closed-loop and HIL planetary landing guidance.

Use publisher pages, Crossref metadata, IEEE Xplore, AIAA Aerospace Research Central, NASA NTRS, arXiv only for preprints, and official solver documentation. Record whether a source is peer reviewed, a preprint, a standard/manual, or a hardware datasheet. Do not infer claims from search snippets.

Implement `validate_rows(rows)` with required columns:

```python
REQUIRED = ("source_id", "year", "venue", "doi", "url", "theme", "method",
            "problem", "hardware", "evidence", "relevance", "gap", "verification")

def validate_rows(rows):
    failures = []
    seen = set()
    for index, row in enumerate(rows, 2):
        for field in REQUIRED:
            if field not in row or (field not in {"doi", "url"} and not row[field].strip()):
                failures.append(f"row {index}: missing {field}")
        if not row.get("doi", "").strip() and not row.get("url", "").strip():
            failures.append(f"row {index}: DOI or stable URL required")
        identity = row.get("doi", "").strip().lower() or row.get("url", "").strip()
        if identity in seen:
            failures.append(f"row {index}: duplicate source identity")
        seen.add(identity)
    return failures
```

The CLI reads the CSV, validates it, verifies every `source_id` exists in `paper/refs.bib`, and exits nonzero on any missing or duplicate source.

- [x] **Step 4: Conduct and verify the first literature pass**

Populate the matrix with at least 40 verified sources, including foundational work and publications from 2021 through the search date. For each candidate research contribution, record the nearest prior method, its evaluation scope, and the precise unresolved gap. Add only verified bibliographic metadata to `paper/refs.bib`.

Run: `python3 -m unittest tests.test_literature_matrix -v && python3 research/literature/check_literature.py`

Expected: tests pass; all rows have traceable identities and matching BibTeX entries.

- [x] **Step 5: Commit the research map**

```bash
git add research/literature paper/refs.bib tests/test_literature_matrix.py
git commit -m "research: 建立轨迹优化系统文献证据矩阵"
```

- [x] **Step 6: Use the matrix as an algorithm gate**

Before any Stage B algorithm experiment, add a row to its plan stating the nearest three prior methods, the new hypothesis, differentiating mechanism, comparison baseline, and falsification criterion. Reject a candidate contribution when the literature matrix already contains the same mechanism and evidence scope without a defensible distinction.

## Task 1: Define Scenario and Result Contracts

**Files:**
- Create: `experiments/__init__.py`
- Create: `experiments/contracts.py`
- Test: `tests/test_experiment_contracts.py`

- [x] **Step 1: Write failing contract tests**

```python
# tests/test_experiment_contracts.py
import unittest

from experiments.contracts import ContractError, validate_result, validate_scenario


class ContractTests(unittest.TestCase):
    def test_valid_scenario(self):
        scenario = {
            "schema_version": 1,
            "scenario_id": "near_nominal_v1",
            "kind": "monte_carlo",
            "seed": 42,
            "sample_count": 100,
            "nominal": {"r0_m": [1500.0, 0.0, 2000.0], "v0_mps": [-75.0, 0.0, 100.0]},
            "perturbations": {
                "r0_m": {"distribution": "uniform_delta", "half_width": [200.0, 0.0, 200.0]},
                "v0_mps": {"distribution": "uniform_delta", "half_width": [20.0, 0.0, 20.0]},
            },
            "solver": "cvxpy_ecos",
            "tolerances": {"terminal_m": 1e-5, "terminal_mps": 1e-5,
                           "dynamics": 1e-6, "cone": 1e-7, "mass_kg": 1e-4},
        }
        validate_scenario(scenario)

    def test_rejects_ambiguous_distribution(self):
        with self.assertRaisesRegex(ContractError, "distribution"):
            validate_scenario({"schema_version": 1, "scenario_id": "x", "kind": "monte_carlo",
                               "seed": 1, "sample_count": 1, "nominal": {},
                               "perturbations": {"r0_m": {"distribution": "random"}},
                               "solver": "cvxpy_ecos", "tolerances": {}})

    def test_failure_result_keeps_input_and_reason(self):
        validate_result({
            "schema_version": 1, "scenario_id": "near_nominal_v1", "sample_id": 3,
            "input": {"r0_m": [1500.0, 0.0, 2000.0], "v0_mps": [-75.0, 0.0, 100.0]},
            "solver": "cvxpy_ecos", "solver_status": "infeasible",
            "classification": "solver_infeasible", "success": False,
            "metrics": {}, "provenance": {"manifest_sha256": "a" * 64},
        })


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the tests and confirm the import failure**

Run: `python3 -m unittest tests.test_experiment_contracts -v`

Expected: `ModuleNotFoundError: No module named 'experiments.contracts'`.

- [x] **Step 3: Implement strict contracts**

```python
# experiments/contracts.py
class ContractError(ValueError):
    pass


def _require(mapping, keys, label):
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ContractError(f"{label} missing fields: {', '.join(missing)}")


def validate_scenario(value):
    _require(value, ("schema_version", "scenario_id", "kind", "seed", "sample_count",
                     "nominal", "perturbations", "solver", "tolerances"), "scenario")
    if value["schema_version"] != 1 or value["kind"] != "monte_carlo":
        raise ContractError("unsupported scenario schema or kind")
    if not isinstance(value["seed"], int) or value["sample_count"] < 1:
        raise ContractError("seed and sample_count must be positive integers")
    _require(value["nominal"], ("r0_m", "v0_mps"), "nominal")
    for name in ("r0_m", "v0_mps"):
        perturbation = value["perturbations"].get(name, {})
        if perturbation.get("distribution") != "uniform_delta":
            raise ContractError(f"{name} distribution must be uniform_delta")
        if len(perturbation.get("half_width", [])) != 3:
            raise ContractError(f"{name} half_width must have three values")
    required_tolerances = ("terminal_m", "terminal_mps", "dynamics", "cone", "mass_kg")
    _require(value["tolerances"], required_tolerances, "tolerances")


def validate_result(value):
    _require(value, ("schema_version", "scenario_id", "sample_id", "input", "solver",
                     "solver_status", "classification", "success", "metrics", "provenance"),
             "result")
    _require(value["input"], ("r0_m", "v0_mps"), "result input")
    digest = value["provenance"].get("manifest_sha256", "")
    if len(digest) != 64:
        raise ContractError("manifest_sha256 must contain 64 hexadecimal characters")
    if value["success"] and value["classification"] != "success":
        raise ContractError("successful result must use success classification")
```

Create an empty `experiments/__init__.py`.

- [x] **Step 4: Run the contract tests**

Run: `python3 -m unittest tests.test_experiment_contracts -v`

Expected: 3 tests pass.

- [x] **Step 5: Commit the contracts**

```bash
git add experiments/__init__.py experiments/contracts.py tests/test_experiment_contracts.py
git commit -m "feat: 定义实验场景与结果契约"
```

## Task 2: Add the Canonical Near-Nominal Scenario

**Files:**
- Create: `experiments/scenarios/near_nominal_v1.json`
- Create: `experiments/scenario_loader.py`
- Test: `tests/test_scenario_loader.py`

- [x] **Step 1: Write deterministic sampling tests**

```python
# tests/test_scenario_loader.py
import unittest
from pathlib import Path

from experiments.scenario_loader import load_scenario, sample_inputs


class ScenarioLoaderTests(unittest.TestCase):
    def test_manifest_is_deterministic(self):
        path = Path("experiments/scenarios/near_nominal_v1.json")
        first, first_hash = load_scenario(path)
        second, second_hash = load_scenario(path)
        self.assertEqual(first, second)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 64)

    def test_samples_are_reproducible_and_keep_symmetry(self):
        scenario, _ = load_scenario(Path("experiments/scenarios/near_nominal_v1.json"))
        samples = sample_inputs(scenario, count=2)
        self.assertEqual(samples, sample_inputs(scenario, count=2))
        self.assertEqual(samples[0]["r0_m"][1], 0.0)
        self.assertEqual(samples[0]["v0_mps"][1], 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test and confirm the missing loader**

Run: `python3 -m unittest tests.test_scenario_loader -v`

Expected: import failure for `experiments.scenario_loader`.

- [x] **Step 3: Add the canonical manifest and loader**

```json
{
  "schema_version": 1,
  "scenario_id": "near_nominal_v1",
  "kind": "monte_carlo",
  "seed": 42,
  "sample_count": 1000,
  "nominal": {"r0_m": [1500.0, 0.0, 2000.0], "v0_mps": [-75.0, 0.0, 100.0]},
  "perturbations": {
    "r0_m": {"distribution": "uniform_delta", "half_width": [200.0, 0.0, 200.0]},
    "v0_mps": {"distribution": "uniform_delta", "half_width": [20.0, 0.0, 20.0]}
  },
  "solver": "cvxpy_ecos",
  "tolerances": {"terminal_m": 0.00001, "terminal_mps": 0.00001,
                 "dynamics": 0.000001, "cone": 0.0000001, "mass_kg": 0.0001}
}
```

```python
# experiments/scenario_loader.py
import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.contracts import validate_scenario


def load_scenario(path: Path):
    raw = path.read_bytes()
    scenario = json.loads(raw)
    validate_scenario(scenario)
    return scenario, hashlib.sha256(raw).hexdigest()


def sample_inputs(scenario, count=None):
    count = scenario["sample_count"] if count is None else count
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
```

- [x] **Step 4: Run deterministic loader tests**

Run: `python3 -m unittest tests.test_scenario_loader -v`

Expected: 2 tests pass.

- [x] **Step 5: Commit the scenario definition**

```bash
git add experiments/scenarios/near_nominal_v1.json experiments/scenario_loader.py tests/test_scenario_loader.py
git commit -m "feat: 固化近标称蒙特卡洛场景"
```

## Task 3: Audit Physical and Numerical Solution Quality

**Files:**
- Create: `experiments/solution_audit.py`
- Test: `tests/test_solution_audit.py`
- Modify: `MarsLanding/mars_solve.py`

- [x] **Step 1: Write audit classification tests**

```python
# tests/test_solution_audit.py
import unittest

from experiments.solution_audit import classify_metrics


TOL = {"terminal_m": 1e-5, "terminal_mps": 1e-5,
       "dynamics": 1e-6, "cone": 1e-7, "mass_kg": 1e-4}


class AuditTests(unittest.TestCase):
    def test_success_requires_every_metric(self):
        metrics = {"terminal_position_m": 1e-7, "terminal_velocity_mps": 1e-7,
                   "max_dynamics_residual": 1e-8, "max_cone_violation": 0.0,
                   "mass_bound_violation_kg": 0.0}
        self.assertEqual(classify_metrics("optimal", metrics, TOL), "success")

    def test_optimal_status_does_not_hide_cone_failure(self):
        metrics = {"terminal_position_m": 1e-7, "terminal_velocity_mps": 1e-7,
                   "max_dynamics_residual": 1e-8, "max_cone_violation": 1e-4,
                   "mass_bound_violation_kg": 0.0}
        self.assertEqual(classify_metrics("optimal", metrics, TOL), "physical_violation")

    def test_solver_failure_is_distinct(self):
        self.assertEqual(classify_metrics("infeasible", {}, TOL), "solver_infeasible")
        self.assertEqual(classify_metrics("solver_error", {}, TOL), "solver_error")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the audit tests and confirm failure**

Run: `python3 -m unittest tests.test_solution_audit -v`

Expected: import failure for `experiments.solution_audit`.

- [x] **Step 3: Implement classification and metric calculation**

Implement `classify_metrics(status, metrics, tolerances)` with these exact rules:

```python
def classify_metrics(status, metrics, tolerances):
    if status in {"infeasible", "infeasible_inaccurate"}:
        return "solver_infeasible"
    if status != "optimal":
        return "solver_error"
    limits = {
        "terminal_position_m": "terminal_m",
        "terminal_velocity_mps": "terminal_mps",
        "max_dynamics_residual": "dynamics",
        "max_cone_violation": "cone",
        "mass_bound_violation_kg": "mass_kg",
    }
    if any(abs(metrics[name]) > tolerances[tolerance]
           for name, tolerance in limits.items()):
        return "physical_violation"
    return "success"
```

Add `compute_metrics(solution)` that consumes NumPy arrays `r`, `v`, `z`, `u`, and `sigma`, recomputes all discrete dynamics with `mars_params`, evaluates `max(0, ||[ry,rz]||-rx*tan(theta))`, `max(0, ||u||-sigma)`, terminal norms, and dry/initial mass violations. Modify `solve_cvxpy` through a new optional `return_full=False` argument; when true, return a dictionary containing these arrays and ECOS iteration metadata without changing the existing default return tuple.

- [x] **Step 4: Run audit and existing solver checks**

Run: `python3 -m unittest tests.test_solution_audit -v`

Expected: 3 tests pass.

Run: `bash ci/validate.sh`

Expected: all existing solver checks pass at approximately 400.7 kg.

- [x] **Step 5: Commit solution auditing**

```bash
git add experiments/solution_audit.py tests/test_solution_audit.py MarsLanding/mars_solve.py
git commit -m "feat: 审计轨迹约束与终端残差"
```

## Task 4: Produce Immutable Per-Sample Monte Carlo Results

**Files:**
- Create: `experiments/ecos_adapter.py`
- Create: `experiments/run_monte_carlo.py`
- Test: `tests/test_monte_carlo_runner.py`
- Modify: `MarsLanding/mars_robustness.py`

- [x] **Step 1: Write a runner test using a fake solver**

```python
# tests/test_monte_carlo_runner.py
import json
import tempfile
import unittest
from pathlib import Path

from experiments.run_monte_carlo import run_experiment


class RunnerTests(unittest.TestCase):
    def test_every_attempt_writes_one_record(self):
        def fake_solver(sample, scenario, digest):
            return {"schema_version": 1, "scenario_id": scenario["scenario_id"],
                    "sample_id": sample["sample_id"],
                    "input": {"r0_m": sample["r0_m"], "v0_mps": sample["v0_mps"]},
                    "solver": scenario["solver"], "solver_status": "infeasible",
                    "classification": "solver_infeasible", "success": False,
                    "metrics": {}, "provenance": {"manifest_sha256": digest}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            run_experiment(Path("experiments/scenarios/near_nominal_v1.json"),
                           output, 3, fake_solver)
            records = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual([record["sample_id"] for record in records], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the runner test and confirm failure**

Run: `python3 -m unittest tests.test_monte_carlo_runner -v`

Expected: import failure for `experiments.run_monte_carlo`.

- [x] **Step 3: Implement atomic JSONL execution**

`run_experiment(manifest_path, output_path, count, solver)` must load and hash the manifest, generate samples, reject an existing output path, write each validated result to `output_path.with_suffix('.jsonl.tmp')`, flush after each record, and rename the temporary file only after all attempts finish. The CLI must be:

```bash
python3 -m experiments.run_monte_carlo \
  --scenario experiments/scenarios/near_nominal_v1.json \
  --output experiments/results/near_nominal_v1.jsonl \
  --count 1000
```

`ecos_adapter.solve_sample` must call the full-output CVXPY+ECOS path, time only the documented solve scope using `time.perf_counter_ns`, compute audit metrics, classify the result, and preserve exceptions as `solver_error` records. Add platform, Python, NumPy, CVXPY, ECOS, git commit, manifest digest, elapsed nanoseconds, and ECOS iteration count to provenance/metrics.

Replace the implementation of `mars_robustness.monte_carlo(n_samples)` with a compatibility wrapper that runs the canonical manifest into a temporary JSONL file and returns the aggregated success rate and conditional mean fuel. Keep `sensitivity()` independent.

- [x] **Step 4: Run unit tests and an 8-sample smoke experiment**

Run: `python3 -m unittest tests.test_monte_carlo_runner -v`

Expected: 1 test passes.

Run: `python3 -m experiments.run_monte_carlo --scenario experiments/scenarios/near_nominal_v1.json --output /tmp/near_nominal_smoke.jsonl --count 8`

Expected: 8 valid JSON lines, including records for failures.

- [x] **Step 5: Commit the runner and adapter**

```bash
git add experiments/ecos_adapter.py experiments/run_monte_carlo.py \
  tests/test_monte_carlo_runner.py MarsLanding/mars_robustness.py
git commit -m "feat: 记录逐样本蒙特卡洛证据"
```

## Task 5: Aggregate Statistics and Failure Taxonomy

**Files:**
- Create: `experiments/aggregate_results.py`
- Test: `tests/test_aggregate_results.py`

- [x] **Step 1: Write exact aggregation tests**

```python
# tests/test_aggregate_results.py
import unittest

from experiments.aggregate_results import aggregate


class AggregateTests(unittest.TestCase):
    def test_counts_failures_and_conditions_fuel_on_success(self):
        records = [
            {"success": True, "classification": "success", "metrics": {"fuel_kg": 400.0}},
            {"success": True, "classification": "success", "metrics": {"fuel_kg": 402.0}},
            {"success": False, "classification": "solver_infeasible", "metrics": {}},
            {"success": False, "classification": "physical_violation", "metrics": {"fuel_kg": 999.0}},
        ]
        summary = aggregate(records)
        self.assertEqual(summary["attempted"], 4)
        self.assertEqual(summary["successful"], 2)
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertEqual(summary["fuel_kg"]["mean"], 401.0)
        self.assertEqual(summary["classifications"]["solver_infeasible"], 1)
        self.assertLess(summary["success_rate_wilson_95"][0], 0.5)
        self.assertGreater(summary["success_rate_wilson_95"][1], 0.5)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the aggregation test and confirm failure**

Run: `python3 -m unittest tests.test_aggregate_results -v`

Expected: import failure for `experiments.aggregate_results`.

- [x] **Step 3: Implement aggregation**

Implement `aggregate(records)` with attempted/successful counts, classification counts, success rate, 95% Wilson interval using `z=1.959963984540054`, and conditional successful fuel count/mean/sample standard deviation/min/max. The CLI reads JSONL, writes canonical sorted/indented JSON, embeds the input SHA-256 digest, and refuses to overwrite an existing summary.

- [x] **Step 4: Verify aggregation and deterministic serialization**

Run: `python3 -m unittest tests.test_aggregate_results -v`

Expected: 1 test passes.

Run: `python3 -m experiments.aggregate_results /tmp/near_nominal_smoke.jsonl /tmp/near_nominal_smoke.summary.json`

Expected: summary reports `attempted: 8`, a Wilson interval, and explicit failure classifications.

- [x] **Step 5: Commit statistical aggregation**

```bash
git add experiments/aggregate_results.py tests/test_aggregate_results.py
git commit -m "feat: 汇总鲁棒性统计与失败分类"
```

## Task 6: Protect the Handwritten Matrix Asset

**Files:**
- Create: `docs/provenance/handwritten-matrix.md`
- Modify: `MarsLanding/check_model_consistency.py`
- Test: `tests/test_handwritten_asset.py`

- [x] **Step 1: Write build-graph protection tests**

```python
# tests/test_handwritten_asset.py
import unittest
from pathlib import Path

from MarsLanding.check_model_consistency import validate_handwritten_asset


class HandwrittenAssetTests(unittest.TestCase):
    def test_current_build_keeps_independent_targets(self):
        root = Path(__file__).resolve().parents[1]
        failures = validate_handwritten_asset(
            (root / "CMakeLists.txt").read_text(),
            (root / "MarsLanding/MarsLanding.c").read_text(),
        )
        self.assertEqual(failures, [])

    def test_generated_header_in_handwritten_source_is_rejected(self):
        failures = validate_handwritten_asset(
            'set(USER_SOURCES "MarsLanding/MarsLanding.c" "MarsLanding/CRM2CCM.c")\n'
            'add_executable(ecos_avx ${ALL_SOURCES})\n'
            'add_executable(ecos_auto MarsLanding/MarsLandingAuto.c)\n',
            '#include "MarsLandingAutoData.h"\n',
        )
        self.assertTrue(any("生成矩阵" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the protection tests and confirm failure**

Run: `python3 -m unittest tests.test_handwritten_asset -v`

Expected: import failure for `validate_handwritten_asset`.

- [x] **Step 3: Implement semantic protection and provenance documentation**

`validate_handwritten_asset(cmake, source)` must require both `MarsLanding/MarsLanding.c` and `MarsLanding/CRM2CCM.c` in `USER_SOURCES`, require `ecos_avx` and `ecos_scalar` to derive from `ALL_SOURCES`, require `ecos_auto` to derive from `MarsLandingAuto.c`, and reject `MarsLandingAutoData.h` or generated-data includes in the handwritten source. Call it from `main()` and report every failure.

Document authorship, CRS construction, CRS→CCS conversion, allowed validation, prohibited replacement, and review requirements in `docs/provenance/handwritten-matrix.md`. Do not use a source hash because legitimate manual maintenance must remain possible.

- [x] **Step 4: Run protection and model checks**

Run: `python3 -m unittest tests.test_handwritten_asset -v && python3 MarsLanding/check_model_consistency.py`

Expected: 2 tests pass and the model consistency checker succeeds.

- [x] **Step 5: Commit the asset guard**

```bash
git add docs/provenance/handwritten-matrix.md MarsLanding/check_model_consistency.py tests/test_handwritten_asset.py
git commit -m "test: 保护原始手写矩阵实现"
```

## Task 7: Establish Host Benchmark Evidence

**Files:**
- Create: `experiments/benchmark_protocol.json`
- Create: `experiments/benchmark_host.py`
- Test: `tests/test_benchmark_protocol.py`

- [x] **Step 1: Write protocol validation tests**

```python
# tests/test_benchmark_protocol.py
import unittest

from experiments.benchmark_host import summarize_ns, validate_protocol


class BenchmarkProtocolTests(unittest.TestCase):
    def test_required_measurement_scope(self):
        validate_protocol({"schema_version": 1, "warmup_runs": 10, "measured_runs": 1000,
                           "clock": "CLOCK_MONOTONIC_RAW",
                           "scopes": ["matrix_update", "setup", "solve", "control_extract", "end_to_end"]})

    def test_percentiles_and_maximum(self):
        summary = summarize_ns([10, 20, 30, 40, 50])
        self.assertEqual(summary["count"], 5)
        self.assertEqual(summary["p50_ns"], 30)
        self.assertEqual(summary["max_ns"], 50)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run protocol tests and confirm failure**

Run: `python3 -m unittest tests.test_benchmark_protocol -v`

Expected: import failure for `experiments.benchmark_host`.

- [x] **Step 3: Implement protocol and host metadata capture**

The protocol JSON must fix 10 warmups, 1000 measured runs, `CLOCK_MONOTONIC_RAW`, five named scopes, double precision, Release build, no outlier deletion, and p50/p95/p99/max reporting. `benchmark_host.py` must validate these fields, calculate nearest-rank percentiles, capture `/proc/cpuinfo`, compiler/CMake versions, git commit, executable SHA-256, command, environment, and raw nanosecond samples. It must never label N150 data as ARM/MCU data.

The first implementation may ingest raw scope samples emitted by executables; it must not invent unavailable scope timings. Missing scopes are recorded as `not_measured`, preventing unsupported paper claims.

- [x] **Step 4: Run benchmark contract tests**

Run: `python3 -m unittest tests.test_benchmark_protocol -v`

Expected: 2 tests pass.

- [x] **Step 5: Commit benchmark evidence support**

```bash
git add experiments/benchmark_protocol.json experiments/benchmark_host.py tests/test_benchmark_protocol.py
git commit -m "feat: 建立主机基准证据协议"
```

## Task 8: Add the Manuscript Claim Ledger

**Files:**
- Create: `paper/evidence/claims.json`
- Create: `paper/evidence/check_claims.py`
- Test: `tests/test_claim_ledger.py`
- Modify: `paper/chapters/ch5_results.tex`

- [x] **Step 1: Write ledger validation tests**

```python
# tests/test_claim_ledger.py
import unittest

from paper.evidence.check_claims import validate_claims


class ClaimLedgerTests(unittest.TestCase):
    def test_quantitative_claim_requires_source_and_command(self):
        failures = validate_claims([{"claim_id": "nominal-fuel", "value": "400.7 kg",
                                     "source": "experiments/results/nominal.summary.json",
                                     "command": "bash ci/validate.sh", "scope": "host measured"}])
        self.assertEqual(failures, [])

    def test_unverified_hardware_claim_is_rejected(self):
        failures = validate_claims([{"claim_id": "m7-time", "value": "5 ms",
                                     "source": "", "command": "", "scope": "Cortex-M7 measured"}])
        self.assertTrue(failures)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run ledger tests and confirm failure**

Run: `python3 -m unittest tests.test_claim_ledger -v`

Expected: import failure for `paper.evidence.check_claims`.

- [x] **Step 3: Implement the ledger and reconcile Monte Carlo prose**

`claims.json` must initially include nominal fuel, solver agreement, N150 solve timing scope, near-nominal scenario definition, Monte Carlo success rate, conditional fuel statistics, and handwritten/automatic model roles. Each entry contains `claim_id`, `manuscript_files`, `value`, `scope`, `source`, `command`, and `status`, where status is one of `verified`, `superseded`, or `future_work`.

`check_claims.py` must reject missing fields, reject `verified` entries without an existing source and nonempty command, and scan manuscript files for the known superseded values `401.2 kg`, `8.3 kg`, `8 microseconds`, and `8 $\\mu$s`.

Run the canonical 1000-sample confirmation scenario once the pipeline is stable and aggregate it. Preserve the raw records as deterministic gzip (`gzip -n -9`) at `experiments/results/near_nominal_v1.jsonl.gz`, commit the compressed records and uncompressed summary, and record SHA-256 digests for both. Then replace the Monte Carlo subsection with the exact manifest definition, attempted/successful counts, Wilson interval, conditional fuel distribution, failure taxonomy, dataset digest, and generation command. Do not describe solver infeasibility as numerical non-convergence without evidence.

- [x] **Step 4: Verify ledger and manuscript build**

Run: `python3 -m unittest tests.test_claim_ledger -v && python3 paper/evidence/check_claims.py`

Expected: tests and ledger validation pass.

Run: `cd paper && xelatex -interaction=nonstopmode -halt-on-error mars_landing_socp.tex && xelatex -interaction=nonstopmode -halt-on-error mars_landing_socp.tex`

Expected: PDF builds without undefined references or overfull boxes.

- [x] **Step 5: Commit evidence-backed manuscript results**

```bash
git add paper/evidence paper/chapters/ch5_results.tex paper/mars_landing_socp.pdf \
  experiments/results tests/test_claim_ledger.py
git commit -m "docs: 以可追溯证据更新鲁棒性结果"
```

## Task 9: Integrate CI and Agent Workflow

**Files:**
- Modify: `ci/validate.sh`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `tests/test_ci_contract.py`

- [x] **Step 1: Write a CI contract test**

```python
# tests/test_ci_contract.py
import unittest
from pathlib import Path


class CiContractTests(unittest.TestCase):
    def test_ci_runs_evidence_and_asset_gates(self):
        source = Path("ci/validate.sh").read_text()
        for command in ("python3 -m unittest discover -s tests -v",
                        "python3 paper/evidence/check_claims.py",
                        "python3 MarsLanding/check_model_consistency.py"):
            self.assertIn(command, source)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the CI contract test and confirm failure**

Run: `python3 -m unittest tests.test_ci_contract -v`

Expected: failure because the new commands are absent from `ci/validate.sh`.

- [x] **Step 3: Add quick and confirmation gates**

At the start of `ci/validate.sh`, run unit discovery, the model/handwritten asset checker, and the claim ledger. Replace the old 20-sample `>40%` Monte Carlo gate with an 8-sample deterministic contract smoke that checks record count/schema only. Add `ci/validate.sh --confirmation` to validate the frozen 1000-sample dataset digest and regenerate its summary without rerunning it. Keep expensive experiment generation as an explicit release command rather than ordinary CI.

Document these entry points in README and add AGENTS rules requiring: scenario manifests before experiments, immutable failed-sample records, claim ledger updates with manuscript changes, no hardware extrapolation, and no replacement of `MarsLanding/MarsLanding.c`.

- [x] **Step 4: Run all verification gates**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass.

Run: `bash ci/validate.sh`

Expected: all C/Python solver, contract, claim, and provenance checks pass.

Run: `bash ci/validate.sh --confirmation`

Expected: frozen dataset digest and regenerated summary match committed evidence.

Run: `git diff --check`

Expected: no whitespace errors.

- [x] **Step 5: Commit the integrated workflow**

```bash
git add ci/validate.sh README.md AGENTS.md tests/test_ci_contract.py
git commit -m "ci: 强制实验与论文证据门槛"
```

## Task 10: Stage A Completion Audit

**Files:**
- Modify: `docs/superpowers/specs/2026-07-13-top-tier-research-engineering-design.md`
- Create: `docs/evidence/stage-a-audit.md`

- [x] **Step 1: Run the complete evidence audit**

Run:

```bash
python3 -m unittest discover -s tests -v
bash ci/validate.sh
bash ci/validate.sh --confirmation
python3 paper/evidence/check_claims.py
git diff --check
```

Expected: every command exits zero; the solver matrix still reports approximately 400.7 kg; the manuscript claim ledger and frozen dataset digest pass.

- [x] **Step 2: Inspect the authoritative artifacts**

Verify that the frozen summary count equals the manifest count, every JSONL line validates, failure classifications sum to attempted samples, successful fuel statistics exclude failures, and the PDF Monte Carlo text matches the summary exactly. Verify CMake still builds `ecos_avx`/`ecos_scalar` from `MarsLanding.c` plus `CRM2CCM.c`, and `ecos_auto` from the generated-data path.

- [x] **Step 3: Record the audit**

Create `docs/evidence/stage-a-audit.md` containing the exact commit, commands, pass counts, dataset/manifest/PDF SHA-256 digests, remaining limitations, and the statement that Stage A establishes evidence infrastructure but does not yet prove target-hardware real-time performance or closed-loop flight readiness.

- [x] **Step 4: Mark only Stage A complete in the design**

Add a dated status block to the design document linking the audit. Keep Stages B-D explicitly active; do not claim the long-term project goal is complete.

- [x] **Step 5: Commit and push the Stage A audit**

```bash
git add docs/evidence/stage-a-audit.md \
  docs/superpowers/specs/2026-07-13-top-tier-research-engineering-design.md
git commit -m "docs: 完成阶段A证据基线审计"
git push origin master
```

## Post-Stage-A Parallel Plans

After Task 10, create four separate reviewed plans using the common contracts:

1. `stage-b-algorithm-ablation.md`: scaling, warm start, symbolic reuse, three problem sizes.
2. `stage-b-embedded-benchmark.md`: staged timing, memory, ARM/RISC-V target evidence.
3. `stage-b-closed-loop-robustness.md`: navigation/actuator disturbances and replanning.
4. `stage-b-paper-artifact.md`: generated tables/figures, environment lock, artifact entry points.

Each plan must retain the unchanged handwritten implementation as the primary C baseline and must pass the Stage A claim and provenance gates.

Literature research continues across all four plans. Each plan begins with an updated search pass and ends by linking every novelty claim to the literature matrix; publication recency is rechecked before manuscript freeze.
