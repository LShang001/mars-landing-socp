import hashlib
import json
import math
import unittest
from unittest import mock

from experiments.benchmark_host import build_evidence, summarize_ns, validate_protocol


SCOPES = ["matrix_update", "setup", "solve", "control_extract", "end_to_end"]


def valid_protocol():
    return {
        "schema_version": 1,
        "evidence_kind": "host_measured",
        "warmup_runs": 10,
        "measured_runs": 1000,
        "clock": "CLOCK_MONOTONIC_RAW",
        "scopes": SCOPES,
        "precision": "double",
        "build_type": "Release",
        "outlier_policy": "none",
        "statistics": ["p50", "p95", "p99", "max"],
        "forbidden_platform_labels": [
            "ARM", "ARM64", "AARCH64", "CORTEX", "RISC-V", "MCU", "EMBEDDED"
        ],
    }


class BenchmarkProtocolTests(unittest.TestCase):
    def test_accepts_only_fixed_host_protocol(self):
        validate_protocol(valid_protocol())

        for field, invalid in (
            ("warmup_runs", 9), ("measured_runs", 999),
            ("clock", "CLOCK_MONOTONIC"), ("precision", "float"),
            ("build_type", "Debug"), ("outlier_policy", "iqr"),
            ("evidence_kind", "mcu_measured"),
        ):
            protocol = valid_protocol()
            protocol[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_protocol(protocol)

        protocol = valid_protocol()
        protocol["notes"] = "unexpected"
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_protocol(protocol)

    def test_rejects_missing_reordered_or_extra_scopes(self):
        for scopes in (SCOPES[:-1], list(reversed(SCOPES)), SCOPES + ["total"]):
            protocol = valid_protocol()
            protocol["scopes"] = scopes
            with self.subTest(scopes=scopes), self.assertRaises(ValueError):
                validate_protocol(protocol)

    def test_nearest_rank_percentiles_and_maximum(self):
        summary = summarize_ns(list(range(1, 101)))
        self.assertEqual(summary, {
            "count": 100, "p50_ns": 50, "p95_ns": 95,
            "p99_ns": 99, "max_ns": 100,
        })

    def test_rejects_empty_nan_and_invalid_samples(self):
        for samples in ([], [math.nan], [math.inf], [-1], [True], [1.5], ["1"]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                summarize_ns(samples)

    def test_percentile_boundaries_duplicates_and_unbounded_integer(self):
        huge = 10 ** 1000
        self.assertEqual(summarize_ns([huge]), {
            "count": 1, "p50_ns": huge, "p95_ns": huge,
            "p99_ns": huge, "max_ns": huge,
        })
        summary = summarize_ns([9, 1, 5, 5, 3])
        self.assertEqual(summary["p50_ns"], 5)
        self.assertEqual(summary["p95_ns"], 9)
        self.assertEqual(summary["p99_ns"], 9)

    def test_missing_scopes_are_explicitly_not_measured(self):
        samples = list(range(1000))
        evidence = build_evidence(
            valid_protocol(), {"solve": samples},
            executable=None, command=["./solver"], environment={"OMP_NUM_THREADS": "1"},
        )
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["evidence_kind"], "host_measured")
        self.assertEqual(evidence["measurements"]["solve"]["raw_ns"], samples)
        self.assertEqual(evidence["measurements"]["setup"], {"status": "not_measured"})
        self.assertNotIn("ARM", evidence["platform"]["labels"])
        self.assertNotIn("MCU", evidence["platform"]["labels"])

    def test_unknown_scope_and_forbidden_platform_label_are_rejected(self):
        with self.assertRaises(ValueError):
            build_evidence(valid_protocol(), {"total": [1]}, executable=None, command=[])
        for label in ("ARM", "arm64", "AArch64", "Cortex-M7", "risc-v", "embedded MCU"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                build_evidence(valid_protocol(), {}, executable=None, command=[],
                               platform_labels=[label])

        evidence = build_evidence(valid_protocol(), {}, executable=None, command=[],
                                  platform_labels=["host", "x86_64"])
        self.assertEqual(evidence["platform"]["labels"], ["host", "x86_64"])

    def test_measured_scope_requires_exact_measured_run_count(self):
        for count in (999, 1001):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "1000"):
                build_evidence(valid_protocol(), {"solve": list(range(count))},
                               executable=None, command=[])

    def test_environment_is_allowlisted_and_secrets_never_appear(self):
        environment = {
            "OMP_NUM_THREADS": "1", "LANG": "C.UTF-8", "HOME": "/tmp/user",
            "OPENAI_API_KEY": "top-secret", "AUTH_PROXY": "secret-proxy",
        }
        evidence = build_evidence(valid_protocol(), {}, executable=None, command=[],
                                  environment=environment)
        self.assertEqual(evidence["environment"], {"OMP_NUM_THREADS": "1", "LANG": "C.UTF-8"})
        self.assertNotIn("top-secret", json.dumps(evidence))
        self.assertNotIn("secret-proxy", json.dumps(evidence))

    @mock.patch("experiments.benchmark_host.platform.machine", return_value="aarch64")
    @mock.patch("experiments.benchmark_host.platform.system", return_value="Linux")
    def test_actual_non_x86_host_requires_target_specific_protocol(self, _system, _machine):
        with self.assertRaisesRegex(ValueError, "target-specific protocol"):
            build_evidence(valid_protocol(), {}, executable=None, command=[])

    def test_machine_allowlist_accepts_only_normalized_x86_names(self):
        for machine in ("x86_64", "AMD64", "i386", "i486", "i586", "i686"):
            with self.subTest(machine=machine), \
                    mock.patch("experiments.benchmark_host.platform.machine", return_value=machine), \
                    mock.patch("experiments.benchmark_host.platform.system", return_value="NonLinuxOS"):
                evidence = build_evidence(valid_protocol(), {}, executable=None, command=[])
                self.assertEqual(evidence["platform"]["machine"], machine)
                self.assertEqual(evidence["platform"]["system"], "NonLinuxOS")

        for machine in ("ppc64le", "s390x", "mips", "unknown", ""):
            with self.subTest(machine=machine), \
                    mock.patch("experiments.benchmark_host.platform.machine", return_value=machine):
                with self.assertRaisesRegex(ValueError, "x86 host benchmark"):
                    build_evidence(valid_protocol(), {}, executable=None, command=[])

    def test_canonical_digest_covers_record_and_disclaims_attestation(self):
        evidence = build_evidence(valid_protocol(), {}, executable=None, command=["./solver"],
                                  environment={"TZ": "UTC"})
        integrity = evidence.pop("integrity")
        canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")
        self.assertEqual(integrity["sha256"], hashlib.sha256(canonical).hexdigest())
        self.assertEqual(integrity["evidence_integrity"],
                         "self-recorded, not cryptographically attested")


if __name__ == "__main__":
    unittest.main()
