import unittest
import os
import subprocess
import tempfile
from pathlib import Path


class CiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = Path("ci/validate.sh").read_text(encoding="utf-8")

    def test_quick_runs_unit_tests_and_both_static_checkers(self):
        self.assertIn("python3 -m unittest discover -s tests", self.script)
        self.assertIn("MarsLanding/check_model_consistency.py", self.script)
        self.assertIn("python3 -m unittest tests.test_handwritten_asset", self.script)

    def test_quick_runs_eight_sample_contract_smoke_and_validates_every_line(self):
        self.assertIn("--count 8", self.script)
        self.assertIn("mktemp", self.script)
        self.assertIn("validate_result", self.script)
        self.assertIn("len(records) != 8", self.script)

    def test_quick_runs_numerical_golden_regressions(self):
        for name in ("ecos_avx", "ecos_scalar", "ecos_auto", "CVXPY+ECOS",
                     "CVXPY+Clarabel", "CasADi+IPOPT"):
            with self.subTest(name=name):
                self.assertIn(name, self.script)
        self.assertIn("ecos_clarabel", self.script)
        self.assertIn("abs(float(value) - 400.7) <= 0.5", self.script)

    def test_claim_checker_is_required_when_present(self):
        self.assertIn("paper/evidence/check_claims.py", self.script)
        self.assertNotIn("check_claims.py || true", self.script)

    def test_quick_fails_before_work_when_claim_checker_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", "ci/validate.sh", "--quick"], text=True,
                capture_output=True, env={**os.environ, "CI_ROOT": directory})
        self.assertEqual(result.returncode, 3)
        self.assertIn("claim checker missing", result.stderr)

    def test_confirmation_exits_three_when_claim_checker_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", "ci/validate.sh", "--confirmation"], text=True,
                capture_output=True, env={**os.environ, "CI_ROOT": directory})
        self.assertEqual(result.returncode, 3)
        self.assertIn("claim checker missing", result.stderr)

    def test_rejects_extra_arguments(self):
        result = subprocess.run(
            ["bash", "ci/validate.sh", "--quick", "extra"], text=True,
            capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_confirmation_requires_frozen_evidence_and_recomputes_summary(self):
        self.assertIn("--confirmation", self.script)
        self.assertIn("experiments/results/near_nominal_v1.jsonl", self.script)
        self.assertIn("experiments/results/near_nominal_v1.jsonl.gz", self.script)
        self.assertIn("experiments/results/near_nominal_v1.summary.json", self.script)
        self.assertIn("paper/evidence/claims.json", self.script)
        self.assertIn("sha256", self.script)
        self.assertIn("len(records) != 1000", self.script)
        self.assertIn("gzip", self.script)
        self.assertIn("validate_result", self.script)
        self.assertIn("16 * 1024 * 1024", self.script)
        self.assertIn("4 * 1024 * 1024", self.script)
        self.assertIn("1 * 1024 * 1024", self.script)
        self.assertIn("python3 -m experiments.aggregate_results", self.script)
        self.assertIn("diff", self.script)

    def test_ci_does_not_gate_on_monte_carlo_success_rate(self):
        self.assertNotIn("success_rate", self.script)
        self.assertNotIn("-gt 40", self.script)
        self.assertNotIn("< 40%", self.script)


if __name__ == "__main__":
    unittest.main()
