import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from paper.evidence.check_claims import (
    MANUSCRIPT_FILES,
    load_claims,
    scan_manuscript_language,
    validate_claims,
)


class ClaimLedgerTests(unittest.TestCase):
    def setUp(self):
        self.source = Path("paper/data/trajectory.json")
        self.valid = {
            "claim_id": "nominal-fuel",
            "manuscript_files": ["paper/chapters/ch5_results.tex"],
            "value": "400.7 kg (numerically consistent; dry-mass violation)",
            "scope": "Nominal CVXPY+ECOS solution audit",
            "source": str(self.source),
            "command": "python3 -m unittest tests.test_solution_audit -v",
            "status": "verified",
            "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "assertions": [
                {"file": str(self.source), "literal": '"fuel"', "purpose": "value"},
                {
                    "file": "paper/chapters/ch5_results.tex",
                    "literal": "干重下界",
                    "purpose": "scope",
                },
            ],
        }

    def test_repository_ledger_is_valid(self):
        self.assertEqual(validate_claims(load_claims()), [])

    def test_solver_agreement_claims_match_their_exact_evidence_scope(self):
        claims = {claim["claim_id"]: claim for claim in load_claims()}
        self.assertNotIn("solver-agreement", claims)
        self.assertEqual(
            claims["c-native-agreement"],
            {
                "claim_id": "c-native-agreement",
                "manuscript_files": ["paper/chapters/ch5_results.tex"],
                "value": "ecos_avx, ecos_scalar, and ecos_auto each report 400.7 kg",
                "scope": (
                    "Three C ECOS executable paths only; numerical objective agreement, "
                    "not physical feasibility or end-to-end validation."
                ),
                "source": "paper/evidence/c_native_nominal.json",
                "command": (
                    "cmake --build build -j4 && ./build/bin/ecos_avx && "
                    "./build/bin/ecos_scalar && ./build/bin/ecos_auto"
                ),
                "status": "verified",
                "source_sha256": "cdc51be920ebb6bb5e0fc39582185f766c8da5961b1e75c51d228ef22a0c2756",
                "assertions": [
                    {
                        "file": "paper/evidence/c_native_nominal.json",
                        "regex": (
                            '\"target\": \"ecos_avx\"[\\s\\S]*'
                            '\"target\": \"ecos_scalar\"[\\s\\S]*'
                            '\"target\": \"ecos_auto\"'
                        ),
                        "purpose": "scope",
                    },
                    {
                        "file": "paper/chapters/ch5_results.tex",
                        "literal": "三个 C 可执行路径当前均报告 400.7 kg",
                        "purpose": "value",
                    },
                ],
            },
        )
        self.assertEqual(
            claims["python-comparison"],
            {
                "claim_id": "python-comparison",
                "manuscript_files": ["paper/chapters/ch5_results.tex"],
                "value": (
                    "CVXPY+ECOS, CVXPY+Clarabel, and CasADi+IPOPT are recorded "
                    "at 400.7 kg"
                ),
                "scope": (
                    "The three Python paths present in solver_comparison.json only; "
                    "numerical objective agreement, not physical feasibility."
                ),
                "source": "paper/data/solver_comparison.json",
                "command": (
                    "python3 -c \"import json; d=json.load(open('paper/data/solver_comparison.json')); "
                    "assert len(d)==3 and all(x['fuel_kg']==400.7 for x in d)\""
                ),
                "status": "verified",
                "source_sha256": "1a07eac6ec168412e78f113b772d885eff7039dec4f6a17c4ca1fe9907ec6b25",
                "assertions": [
                    {
                        "file": "paper/data/solver_comparison.json",
                        "regex": "CVXPY\\+ECOS[\\s\\S]*CVXPY\\+Clarabel[\\s\\S]*CasADi\\+IPOPT",
                        "purpose": "scope",
                    },
                    {
                        "file": "paper/chapters/ch5_results.tex",
                        "literal": "Python comparison 文件中的三条记录也均为 400.7 kg",
                        "purpose": "value",
                    },
                ],
            },
        )

    def test_full_manuscript_rejects_overstrong_solver_agreement_language(self):
        failures = scan_manuscript_language()
        self.assertEqual(failures, [])

    def test_language_gate_includes_sparse_and_embedded_chapters(self):
        self.assertIn("paper/chapters/ch4_sparse_ecos.tex", MANUSCRIPT_FILES)
        self.assertIn("paper/chapters/ch6_embedded.tex", MANUSCRIPT_FILES)

    def test_n150_mean_claim_uses_frozen_limited_evidence(self):
        claim = {item["claim_id"]: item for item in load_claims()}["n150-timing-scope"]
        self.assertEqual(claim["status"], "verified")
        self.assertEqual(claim["source"], "paper/evidence/n150_solve_report.json")
        self.assertIn("source_sha256", claim)
        asserted = {item["file"] for item in claim["assertions"]}
        self.assertEqual(
            asserted,
            {
                "paper/evidence/n150_solve_report.json",
                "paper/chapters/ch1_intro.tex",
                "paper/chapters/ch5_results.tex",
                "paper/chapters/ch6_embedded.tex",
                "paper/chapters/ch7_conclusion.tex",
            },
        )
        self.assertIn("no raw per-iteration samples", claim["scope"])
        self.assertNotRegex(claim["value"], r"p99|WCET")

    def test_language_scan_rejects_acados_and_proof_phrases(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "paper.tex"
            manuscript.write_text(
                "acados 六种求解方案严格一致，全部收敛并验证了无损凸化。",
                encoding="utf-8",
            )
            failures = scan_manuscript_language([manuscript])
        for phrase in ("六种求解", "严格一致", "全部收敛", "验证了无损凸化"):
            self.assertTrue(any(phrase in failure for failure in failures))

    def test_missing_required_field_is_rejected(self):
        claim = dict(self.valid)
        del claim["scope"]
        self.assertTrue(validate_claims([claim]))

    def test_unknown_status_is_rejected(self):
        claim = dict(self.valid, status="draft")
        self.assertTrue(validate_claims([claim]))

    def test_verified_claim_requires_existing_source_and_command(self):
        claim = dict(self.valid, source="missing.json", command="")
        failures = validate_claims([claim])
        self.assertGreaterEqual(len(failures), 2)

    def test_verified_claim_rejects_false_command(self):
        failures = validate_claims([dict(self.valid, command="false")], scan_manuscripts=False)
        self.assertTrue(any("noop" in failure for failure in failures))

    def test_verified_claim_rejects_hash_mismatch(self):
        failures = validate_claims(
            [dict(self.valid, source_sha256="0" * 64)], scan_manuscripts=False
        )
        self.assertTrue(any("SHA-256" in failure for failure in failures))

    def test_verified_claim_rejects_absolute_and_parent_paths(self):
        for source in ("/tmp/evidence.json", "../evidence.json"):
            with self.subTest(source=source):
                failures = validate_claims(
                    [dict(self.valid, source=source)], scan_manuscripts=False
                )
                self.assertTrue(any("repository-relative" in failure for failure in failures))

    def test_assertion_rejects_repo_escape_and_fake_value(self):
        bad = dict(
            self.valid,
            value="999999 kg",
            assertions=[
                {"file": "/tmp/fake", "literal": "999999", "purpose": "value"},
                {
                    "file": "paper/chapters/ch5_results.tex",
                    "literal": "干重下界",
                    "purpose": "scope",
                },
            ],
        )
        failures = validate_claims([bad], scan_manuscripts=False)
        self.assertTrue(any("repository-relative" in failure for failure in failures))
        self.assertTrue(any("source" in failure for failure in failures))

    def test_future_work_does_not_require_generated_dataset(self):
        claim = dict(
            self.valid,
            claim_id="mc-status",
            value="1000-sample confirmation pending",
            source="experiments/results/near_nominal_v1.summary.json",
            command=(
                "python3 -m experiments.run_monte_carlo --scenario "
                "experiments/scenarios/near_nominal_v1.json --output "
                "experiments/results/near_nominal_v1.jsonl --count 1000"
            ),
            status="future_work",
        )
        self.assertEqual(validate_claims([claim], scan_manuscripts=False), [])

    def test_unfrozen_monte_carlo_numbers_cannot_be_verified(self):
        claim = dict(
            self.valid,
            claim_id="mc-success-rate",
            value="59 percent",
            scope="1000-sample Monte Carlo confirmation",
            source="experiments/scenarios/near_nominal_v1.json",
        )
        failures = validate_claims([claim], scan_manuscripts=False)
        self.assertTrue(any("Monte Carlo" in failure for failure in failures))

    def test_verified_monte_carlo_requires_manifest_raw_and_gzip_digests(self):
        claim = dict(
            self.valid,
            claim_id="mc-confirmation",
            source="experiments/results/near_nominal_v1.summary.json",
        )
        failures = validate_claims([claim], scan_manuscripts=False)
        for field in ("manifest_sha256", "raw_sha256", "gzip_sha256"):
            self.assertTrue(any(field in failure for failure in failures))

    def test_known_superseded_values_are_rejected_in_manuscript(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "chapter.tex"
            manuscript.write_text("mean 401.2 kg and std 8.3 kg", encoding="utf-8")
            claim = dict(self.valid, manuscript_files=[str(manuscript)])
            failures = validate_claims([claim])
        self.assertTrue(any("401.2 kg" in failure for failure in failures))
        self.assertTrue(any("8.3 kg" in failure for failure in failures))

    def test_ledger_root_must_be_a_json_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claims.json"
            path.write_text(json.dumps({"claims": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "array"):
                load_claims(path)


if __name__ == "__main__":
    unittest.main()
