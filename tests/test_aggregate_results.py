import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.aggregate_results import aggregate


def result(sample_id, classification="success", fuel=400.0,
           scenario_id="near_nominal_v1", digest="a" * 64):
    success = classification == "success"
    metrics = {"fuel_kg": fuel} if success and fuel is not None else {}
    return {
        "schema_version": 1,
        "scenario_id": scenario_id,
        "sample_id": sample_id,
        "input": {"r0_m": [1500.0, 0.0, 2000.0],
                  "v0_mps": [-75.0, 0.0, 100.0]},
        "solver": "cvxpy_ecos",
        "solver_status": "optimal" if success else classification,
        "classification": classification,
        "success": success,
        "error_type": "Exception" if classification == "solver_error" else "none",
        "metrics": metrics,
        "provenance": {
            "manifest_sha256": digest, "platform": "test", "python_version": "3.12",
            "numpy_version": "2", "cvxpy_version": "1", "ecos_version": "2",
            "git_commit": "deadbeef",
        },
    }


class AggregateTests(unittest.TestCase):
    def test_planned_mixed_summary(self):
        records = [result(0, fuel=399.0), result(1, fuel=401.0),
                   result(2, "solver_infeasible"), result(3, "physical_violation")]
        summary = aggregate(records)
        self.assertEqual(summary["attempted"], 4)
        self.assertEqual(summary["successful"], 2)
        self.assertEqual(summary["classification_counts"], {
            "physical_violation": 1, "solver_infeasible": 1, "success": 2})
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertAlmostEqual(summary["success_rate_wilson_95"]["lower"], 0.15003898915214947)
        self.assertAlmostEqual(summary["success_rate_wilson_95"]["upper"], 0.8499610108478506)
        self.assertEqual(summary["fuel_kg"], {
            "count": 2, "mean": 400.0, "sample_std": math.sqrt(2.0),
            "min": 399.0, "max": 401.0})

    def test_all_failed_has_null_fuel_statistics(self):
        summary = aggregate([result(0, "solver_error")])
        self.assertEqual(summary["successful"], 0)
        self.assertEqual(summary["fuel_kg"], {
            "count": 0, "mean": None, "sample_std": None, "min": None, "max": None})

    def test_single_success_has_zero_sample_std(self):
        self.assertEqual(aggregate([result(0, fuel=400.7)])["fuel_kg"]["sample_std"], 0.0)

    def test_wilson_interval_for_all_success_and_all_failure(self):
        failed = aggregate([result(0, "solver_error"), result(1, "solver_error")])
        passed = aggregate([result(0), result(1)])
        self.assertEqual(failed["success_rate_wilson_95"]["lower"], 0.0)
        self.assertAlmostEqual(failed["success_rate_wilson_95"]["upper"], 0.6576197724933469)
        self.assertAlmostEqual(passed["success_rate_wilson_95"]["lower"], 0.3423802275066531)
        self.assertEqual(passed["success_rate_wilson_95"]["upper"], 1.0)

    def test_rejects_empty_input_and_missing_success_fuel(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            aggregate([])
        with self.assertRaisesRegex(ValueError, "fuel_kg"):
            aggregate([result(0, fuel=None)])

    def test_contract_rejects_nonfinite_fuel(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            aggregate([result(0, fuel=float("nan"))])


class CliTests(unittest.TestCase):
    def run_cli(self, records, output, raw=None):
        input_path = output.parent / "results.jsonl"
        data = raw if raw is not None else "".join(
            json.dumps(item, sort_keys=True) + "\n" for item in records)
        input_path.write_text(data, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-m", "experiments.aggregate_results",
             str(input_path), str(output)], text=True, capture_output=True)
        return completed, input_path, data.encode()

    def test_cli_writes_canonical_deterministic_summary_with_input_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            completed, _, raw = self.run_cli([result(0), result(1, "solver_error")], first)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(first.read_text())
            self.assertEqual(payload["input_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(payload["scenario_id"], "near_nominal_v1")
            self.assertEqual(payload["manifest_sha256"], "a" * 64)
            expected = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
            self.assertEqual(first.read_text(), expected)
            second = root / "second.json"
            completed, _, _ = self.run_cli([result(0), result(1, "solver_error")], second)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_cli_rejects_empty_jsonl_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            completed, _, _ = self.run_cli([], output, raw="")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("cannot aggregate empty results", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertFalse(output.exists())

    def test_cli_reports_contract_error_at_input_line(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            bad = result(1)
            bad["success"] = False
            completed, _, _ = self.run_cli([result(0), bad], output)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("invalid result at line 2", completed.stderr)
            self.assertFalse(output.exists())

    def test_cli_rejects_invalid_utf8_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "results.jsonl"
            output = root / "summary.json"
            input_path.write_bytes(json.dumps(result(0)).encode() + b"\n\xff\n")
            completed = subprocess.run(
                [sys.executable, "-m", "experiments.aggregate_results",
                 str(input_path), str(output)], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("invalid UTF-8 at line 2", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertFalse(output.exists())

    def test_cli_refuses_existing_symlink_and_dangling_symlink(self):
        for dangling in (False, True):
            with self.subTest(dangling=dangling), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / "target.json"
                if not dangling:
                    target.write_text("keep")
                output = root / "summary.json"
                output.symlink_to(target)
                completed, _, _ = self.run_cli([result(0)], output)
                self.assertNotEqual(completed.returncode, 0)
                self.assertTrue(output.is_symlink())
                if not dangling:
                    self.assertEqual(target.read_text(), "keep")

    def test_atomic_publish_fsyncs_file_and_parent_directory(self):
        from experiments.aggregate_results import _atomic_write_new
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with mock.patch("experiments.aggregate_results.os.fsync", wraps=os.fsync) as fsync:
                _atomic_write_new(output, b"{}\n")
            self.assertGreaterEqual(fsync.call_count, 2)

    def test_atomic_publish_removes_temp_before_directory_fsync(self):
        from experiments.aggregate_results import _atomic_write_new
        events = []
        real_link = os.link
        real_unlink = Path.unlink
        real_fsync = os.fsync

        def link(source, destination):
            events.append("link")
            return real_link(source, destination)

        def unlink(path, *args, **kwargs):
            events.append("unlink")
            return real_unlink(path, *args, **kwargs)

        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                events.append("directory_fsync")
            return real_fsync(fd)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with mock.patch("experiments.aggregate_results.os.link", side_effect=link), \
                    mock.patch("pathlib.Path.unlink", side_effect=unlink, autospec=True), \
                    mock.patch("experiments.aggregate_results.os.fsync", side_effect=fsync):
                _atomic_write_new(output, b"{}\n")
        self.assertLess(events.index("link"), events.index("unlink"))
        self.assertLess(events.index("unlink"), events.index("directory_fsync"))

    def test_cli_rejects_duplicate_ids_mixed_inputs_and_overwrite(self):
        cases = [
            ([result(0), result(0)], "duplicate sample_id"),
            ([result(0), result(1, scenario_id="other")], "scenario_id"),
            ([result(0), result(1, digest="b" * 64)], "manifest_sha256"),
        ]
        for records, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "summary.json"
                completed, _, _ = self.run_cli(records, output)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(message, completed.stderr)
                self.assertFalse(output.exists())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            output.write_text("keep")
            completed, _, _ = self.run_cli([result(0)], output)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(output.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
