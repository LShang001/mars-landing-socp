"""Host benchmark evidence schema, summaries, and provenance capture."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


SCOPES = ["matrix_update", "setup", "solve", "control_extract", "end_to_end"]
ENVIRONMENT_ALLOWLIST = {
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "LC_ALL", "LANG", "TZ",
}
SECRET_KEY_FRAGMENTS = {"KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH"}
EXPECTED = {
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


def validate_protocol(protocol: Mapping) -> None:
    """Require the fixed, reproducible host measurement protocol."""
    if not isinstance(protocol, Mapping):
        raise ValueError("protocol must be an object")
    if set(protocol) != set(EXPECTED):
        raise ValueError(f"protocol keys must be exactly {sorted(EXPECTED)}")
    for field, expected in EXPECTED.items():
        if protocol.get(field) != expected:
            raise ValueError(f"{field} must equal {expected!r}")


def summarize_ns(samples: Sequence[int]) -> dict[str, int]:
    """Summarize integer nanoseconds using nearest-rank percentiles."""
    if not samples:
        raise ValueError("samples must not be empty")
    values = []
    for value in samples:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("samples must be finite, non-negative integer nanoseconds")
        values.append(value)
    values.sort()

    def nearest_rank(percent: int) -> int:
        rank = math.ceil(percent / 100 * len(values))
        return values[rank - 1]

    return {
        "count": len(values),
        "p50_ns": nearest_rank(50),
        "p95_ns": nearest_rank(95),
        "p99_ns": nearest_rank(99),
        "max_ns": values[-1],
    }


def _command_output(command: Sequence[str]) -> str | None:
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _sha256(path: str | os.PathLike | None) -> str | None:
    if path is None:
        return None
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def collect_host_metadata(executable: str | os.PathLike | None) -> dict:
    """Capture reproducibility metadata without assigning embedded labels."""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        cpuinfo = None
    system = platform.system()
    machine = platform.machine()
    normalized_machine = machine.strip().lower()
    is_x86 = normalized_machine in {"x86_64", "amd64"} or bool(
        re.fullmatch(r"i[3-6]86", normalized_machine)
    )
    if not is_x86:
        raise ValueError(
            f"machine {machine!r} requires a target-specific protocol; "
            "this recorder is restricted to the x86 host benchmark"
        )
    return {
        "platform": {
            "system": system, "release": platform.release(),
            "machine": machine, "processor": platform.processor(),
            "labels": ["host"],
        },
        "cpuinfo": cpuinfo,
        "compiler_version": _command_output(["cc", "--version"]),
        "cmake_version": _command_output(["cmake", "--version"]),
        "git_commit": _command_output(["git", "rev-parse", "HEAD"]),
        "executable_sha256": _sha256(executable),
    }


def build_evidence(
    protocol: Mapping,
    scope_samples: Mapping[str, Sequence[int]],
    *,
    executable: str | os.PathLike | None,
    command: Sequence[str],
    environment: Mapping[str, str] | None = None,
    platform_labels: Sequence[str] | None = None,
) -> dict:
    """Build host evidence; unavailable scopes remain explicitly unmeasured."""
    validate_protocol(protocol)
    unknown = set(scope_samples) - set(SCOPES)
    if unknown:
        raise ValueError(f"unknown measurement scopes: {sorted(unknown)}")
    labels = list(platform_labels or ["host"])
    forbidden = {label.upper() for label in protocol["forbidden_platform_labels"]}
    if any(word in label.upper() for label in labels for word in forbidden):
        raise ValueError("host evidence cannot carry embedded or non-host architecture labels")

    metadata = collect_host_metadata(executable)
    metadata["platform"]["labels"] = labels
    measurements = {}
    for scope in SCOPES:
        if scope not in scope_samples:
            measurements[scope] = {"status": "not_measured"}
            continue
        raw = list(scope_samples[scope])
        measured_runs = protocol["measured_runs"]
        if len(raw) != measured_runs:
            raise ValueError(f"{scope} must contain exactly {measured_runs} raw samples")
        measurements[scope] = {
            "status": "measured", "raw_ns": raw, "summary": summarize_ns(raw),
        }
    source_environment = os.environ if environment is None else environment
    sanitized_environment = {
        key: value for key, value in source_environment.items()
        if key in ENVIRONMENT_ALLOWLIST
        and not any(fragment in key.upper() for fragment in SECRET_KEY_FRAGMENTS)
    }
    canonical_protocol = json.dumps(
        protocol, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    evidence = {
        "schema_version": 1,
        "evidence_kind": "host_measured",
        "protocol": dict(protocol),
        "protocol_sha256": hashlib.sha256(canonical_protocol).hexdigest(),
        **metadata,
        "command": list(command),
        "environment": sanitized_environment,
        "measurements": measurements,
    }
    canonical_evidence = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    evidence["integrity"] = {
        "sha256": hashlib.sha256(canonical_evidence).hexdigest(),
        "evidence_integrity": "self-recorded, not cryptographically attested",
    }
    return evidence
