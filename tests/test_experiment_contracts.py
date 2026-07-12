import unittest
import json
from pathlib import Path

from experiments.contracts import ContractError, validate_result, validate_scenario


class ContractTests(unittest.TestCase):
    def _scenario(self):
        return json.loads(Path("experiments/scenarios/near_nominal_v1.json").read_text())

    def _result(self):
        return {
            "schema_version": 1, "scenario_id": "near_nominal_v1", "sample_id": 3,
            "input": {"r0_m": [1500.0, 0.0, 2000.0], "v0_mps": [-75.0, 0.0, 100.0]},
            "solver": "cvxpy_ecos", "solver_status": "optimal",
            "classification": "success", "success": True,
            "error_type": "none",
            "metrics": {"fuel_kg": 400.7},
            "provenance": self._provenance(),
        }

    def _provenance(self):
        return {
            "manifest_sha256": "a" * 64, "platform": "Linux-x86_64",
            "python_version": "3.12.3", "numpy_version": "2.0.0",
            "cvxpy_version": "1.6.0", "ecos_version": "2.0.14",
            "git_commit": "b" * 40,
        }

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
            "error_type": "none",
            "metrics": {}, "provenance": self._provenance(),
        })

    def test_rejects_non_hex_manifest_digest(self):
        with self.assertRaisesRegex(ContractError, "64 hexadecimal characters"):
            validate_result({
                "schema_version": 1, "scenario_id": "near_nominal_v1", "sample_id": 3,
                "input": {"r0_m": [1500.0, 0.0, 2000.0], "v0_mps": [-75.0, 0.0, 100.0]},
                "solver": "cvxpy_ecos", "solver_status": "infeasible",
                "classification": "solver_infeasible", "success": False,
                "error_type": "none",
                "metrics": {}, "provenance": {**self._provenance(), "manifest_sha256": "g" * 64},
            })

    def test_result_requires_exact_safe_provenance_strings(self):
        for field in self._provenance():
            with self.subTest(field=field):
                result = self._result()
                del result["provenance"][field]
                with self.assertRaises(ContractError):
                    validate_result(result)
        result = self._result()
        result["provenance"]["platform"] = {"environment": "secret"}
        with self.assertRaises(ContractError):
            validate_result(result)

    def test_result_error_type_is_whitelisted_and_only_used_for_solver_error(self):
        result = self._result()
        result.update(classification="solver_error", success=False,
                      solver_status="exception", error_type="Exception")
        validate_result(result)
        for error_type in ("RuntimeError: secret", "", 1):
            with self.subTest(error_type=error_type):
                result["error_type"] = error_type
                with self.assertRaises(ContractError):
                    validate_result(result)
        result = self._result()
        result["error_type"] = "Exception"
        with self.assertRaises(ContractError):
            validate_result(result)

    def test_rejects_non_integer_sample_count(self):
        for sample_count in (1.5, True):
            with self.subTest(sample_count=sample_count):
                scenario = {
                    "schema_version": 1, "scenario_id": "near_nominal_v1",
                    "kind": "monte_carlo", "seed": 42, "sample_count": sample_count,
                    "nominal": {"r0_m": [1500.0, 0.0, 2000.0],
                                "v0_mps": [-75.0, 0.0, 100.0]},
                    "perturbations": {
                        "r0_m": {"distribution": "uniform_delta", "half_width": [200.0, 0.0, 200.0]},
                        "v0_mps": {"distribution": "uniform_delta", "half_width": [20.0, 0.0, 20.0]},
                    },
                    "solver": "cvxpy_ecos",
                    "tolerances": {"terminal_m": 1e-5, "terminal_mps": 1e-5,
                                   "dynamics": 1e-6, "cone": 1e-7, "mass_kg": 1e-4},
                }
                with self.assertRaisesRegex(ContractError, "sample_count.*positive integer"):
                    validate_scenario(scenario)

    def test_rejects_non_positive_or_boolean_seed(self):
        for seed in (True, 0, -1):
            with self.subTest(seed=seed):
                scenario = {
                    "schema_version": 1, "scenario_id": "near_nominal_v1",
                    "kind": "monte_carlo", "seed": seed, "sample_count": 100,
                    "nominal": {"r0_m": [1500.0, 0.0, 2000.0],
                                "v0_mps": [-75.0, 0.0, 100.0]},
                    "perturbations": {
                        "r0_m": {"distribution": "uniform_delta", "half_width": [200.0, 0.0, 200.0]},
                        "v0_mps": {"distribution": "uniform_delta", "half_width": [20.0, 0.0, 20.0]},
                    },
                    "solver": "cvxpy_ecos",
                    "tolerances": {"terminal_m": 1e-5, "terminal_mps": 1e-5,
                                   "dynamics": 1e-6, "cone": 1e-7, "mass_kg": 1e-4},
                }
                with self.assertRaisesRegex(ContractError, "seed.*positive integer"):
                    validate_scenario(scenario)

    def test_scenario_rejects_unknown_fields(self):
        paths = [(), ("nominal",), ("perturbations",), ("perturbations", "r0_m"),
                 ("tolerances",)]
        for path in paths:
            with self.subTest(path=path):
                scenario = self._scenario()
                target = scenario
                for key in path:
                    target = target[key]
                target["unknown"] = 1
                with self.assertRaisesRegex(ContractError, "unknown fields"):
                    validate_scenario(scenario)

    def test_scenario_rejects_invalid_vectors_and_numeric_domains(self):
        cases = [
            (("nominal", "r0_m"), [1.0, 2.0]),
            (("nominal", "v0_mps"), [1.0, True, 3.0]),
            (("nominal", "r0_m"), [1.0, float("inf"), 3.0]),
            (("perturbations", "r0_m", "half_width"), [1.0, -1.0, 3.0]),
            (("perturbations", "v0_mps", "half_width"), [1.0, float("nan"), 3.0]),
            (("tolerances", "cone"), 0.0),
            (("tolerances", "mass_kg"), float("inf")),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value):
                scenario = self._scenario()
                target = scenario
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ContractError):
                    validate_scenario(scenario)

    def test_scenario_rejects_seed_above_randomstate_range(self):
        scenario = self._scenario()
        scenario["seed"] = 2**32
        with self.assertRaisesRegex(ContractError, "seed"):
            validate_scenario(scenario)

    def test_scenario_rejects_boolean_schema_version(self):
        scenario = self._scenario()
        scenario["schema_version"] = True
        with self.assertRaisesRegex(ContractError, "schema"):
            validate_scenario(scenario)

    def test_result_enforces_strict_schema_and_consistency(self):
        mutations = [
            lambda r: r.update(schema_version=2),
            lambda r: r.update(schema_version=True),
            lambda r: r.update(scenario_id=""),
            lambda r: r.update(sample_id=True),
            lambda r: r.update(sample_id=-1),
            lambda r: r["input"].update(r0_m=[1.0, 2.0]),
            lambda r: r.update(solver=""),
            lambda r: r.update(solver_status=""),
            lambda r: r.update(classification="unknown"),
            lambda r: r.update(success=1),
            lambda r: r.update(success=False),
            lambda r: r.update(classification="solver_error"),
            lambda r: r["metrics"].update(bad=float("nan")),
            lambda r: r["metrics"].update(bad=[1.0]),
            lambda r: r.update(unknown=1),
            lambda r: r["input"].update(unknown=1),
            lambda r: r["provenance"].update(unknown=1),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                result = self._result()
                mutate(result)
                with self.assertRaises(ContractError):
                    validate_result(result)

    def test_failure_classification_requires_false_success(self):
        result = self._result()
        result.update(classification="solver_infeasible", success=False,
                      solver_status="infeasible", metrics={})
        validate_result(result)

    def test_rejects_unhashable_classification_with_contract_error(self):
        for classification in ([], {}):
            with self.subTest(classification=classification):
                result = self._result()
                result["classification"] = classification
                with self.assertRaisesRegex(ContractError, "classification"):
                    validate_result(result)

    def test_rejects_non_string_mapping_keys_with_contract_error(self):
        scenario = self._scenario()
        scenario[1] = "unknown"
        with self.assertRaisesRegex(ContractError, "string keys"):
            validate_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
