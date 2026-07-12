import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from experiments.run_monte_carlo import run_experiment


def _provenance(digest):
    return {
        "manifest_sha256": digest, "platform": "test-platform",
        "python_version": "test", "numpy_version": "test",
        "cvxpy_version": "test", "ecos_version": "test",
        "git_commit": "unknown",
    }


class RunnerTests(unittest.TestCase):
    manifest = Path("experiments/scenarios/near_nominal_v1.json")

    @staticmethod
    def fake_solver(sample, scenario, digest):
        return {
            "schema_version": 1, "scenario_id": scenario["scenario_id"],
            "sample_id": sample["sample_id"],
            "input": {"r0_m": sample["r0_m"], "v0_mps": sample["v0_mps"]},
            "solver": scenario["solver"], "solver_status": "infeasible",
            "classification": "solver_infeasible", "success": False,
            "error_type": "none",
            "metrics": {"elapsed_ns": 1, "ecos_iterations": 0},
            "provenance": _provenance(digest),
        }

    def test_every_attempt_writes_one_valid_record(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            run_experiment(self.manifest, output, 3, self.fake_solver)
            records = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual([record["sample_id"] for record in records], [0, 1, 2])

    def test_existing_output_is_refused_without_calling_solver(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text("original\n")
            with self.assertRaises(FileExistsError):
                run_experiment(self.manifest, output, 1, self.fake_solver)
            self.assertEqual(output.read_text(), "original\n")

    def test_solver_crash_does_not_publish_partial_output(self):
        def crash(sample, scenario, digest):
            if sample["sample_id"] == 1:
                raise RuntimeError("interrupted")
            return self.fake_solver(sample, scenario, digest)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                run_experiment(self.manifest, output, 3, crash)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_target_created_during_run_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"

            def create_target(sample, scenario, digest):
                output.write_text("intruder\n")
                return self.fake_solver(sample, scenario, digest)

            with self.assertRaises(FileExistsError):
                run_experiment(self.manifest, output, 1, create_target)
            self.assertEqual(output.read_text(), "intruder\n")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_dangling_symlink_output_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.symlink_to(Path(directory) / "missing")
            with self.assertRaises(FileExistsError):
                run_experiment(self.manifest, output, 1, self.fake_solver)
            self.assertTrue(output.is_symlink())

    def test_concurrent_publish_has_one_winner_and_no_temp_leaks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            barrier = threading.Barrier(2)
            outcomes = []

            def solver(sample, scenario, digest):
                barrier.wait()
                return self.fake_solver(sample, scenario, digest)

            def run():
                try:
                    run_experiment(self.manifest, output, 1, solver)
                    outcomes.append("published")
                except FileExistsError:
                    outcomes.append("refused")

            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertCountEqual(outcomes, ["published", "refused"])
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_successful_publish_fsyncs_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            with mock.patch("experiments.run_monte_carlo._fsync_directory") as fsync_dir:
                run_experiment(self.manifest, output, 1, self.fake_solver)
            fsync_dir.assert_called_once_with(output.parent)


if __name__ == "__main__":
    unittest.main()
