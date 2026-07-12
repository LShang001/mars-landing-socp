import math
import re
from collections.abc import Mapping
from numbers import Real


class ContractError(ValueError):
    pass


SCENARIO_FIELDS = {
    "schema_version", "scenario_id", "kind", "seed", "sample_count",
    "nominal", "perturbations", "solver", "tolerances",
}
RESULT_FIELDS = {
    "schema_version", "scenario_id", "sample_id", "input", "solver",
    "solver_status", "classification", "success", "error_type", "metrics", "provenance",
}
VECTOR_FIELDS = {"r0_m", "v0_mps"}
PERTURBATION_FIELDS = {"distribution", "half_width"}
TOLERANCE_FIELDS = {"terminal_m", "terminal_mps", "dynamics", "cone", "mass_kg"}
CLASSIFICATIONS = {"success", "solver_infeasible", "solver_error", "physical_violation"}
ERROR_TYPES = {"none", "CvxpySolveError", "Exception"}
PROVENANCE_FIELDS = {
    "manifest_sha256", "platform", "python_version", "numpy_version",
    "cvxpy_version", "ecos_version", "git_commit",
}


def _require_mapping(value, label):
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    non_string_keys = [key for key in value if not isinstance(key, str)]
    if non_string_keys:
        rendered = ", ".join(sorted((repr(key) for key in non_string_keys)))
        raise ContractError(f"{label} must use string keys; invalid keys: {rendered}")


def _require_exact_fields(mapping, fields, label):
    _require_mapping(mapping, label)
    missing = fields - set(mapping)
    if missing:
        raise ContractError(f"{label} missing fields: {', '.join(sorted(missing))}")
    unknown = set(mapping) - fields
    if unknown:
        rendered = ", ".join(sorted((repr(key) for key in unknown)))
        raise ContractError(f"{label} unknown fields: {rendered}")


def _is_finite_real(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _require_vector(value, label, nonnegative=False):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(not _is_finite_real(item) for item in value)):
        raise ContractError(f"{label} must contain three finite real values")
    if nonnegative and any(item < 0 for item in value):
        raise ContractError(f"{label} values must be nonnegative")


def _require_nonempty_string(value, label):
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty string")


def validate_scenario(value):
    _require_exact_fields(value, SCENARIO_FIELDS, "scenario")
    if (type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["kind"] != "monte_carlo"):
        raise ContractError("unsupported scenario schema or kind")
    _require_nonempty_string(value["scenario_id"], "scenario_id")
    _require_nonempty_string(value["solver"], "solver")

    seed = value["seed"]
    sample_count = value["sample_count"]
    if (not isinstance(seed, int) or isinstance(seed, bool)
            or seed < 1 or seed > 2**32 - 1
            or not isinstance(sample_count, int) or isinstance(sample_count, bool)
            or sample_count < 1):
        raise ContractError("seed and sample_count must be positive integers; seed must fit RandomState")

    perturbations = value["perturbations"]
    if isinstance(perturbations, Mapping):
        for name in ("r0_m", "v0_mps"):
            perturbation = perturbations.get(name)
            if (isinstance(perturbation, Mapping)
                    and "distribution" in perturbation
                    and perturbation["distribution"] != "uniform_delta"):
                raise ContractError(f"{name} distribution must be uniform_delta")

    _require_exact_fields(value["nominal"], VECTOR_FIELDS, "nominal")
    _require_exact_fields(perturbations, VECTOR_FIELDS, "perturbations")
    for name in ("r0_m", "v0_mps"):
        _require_vector(value["nominal"][name], f"nominal {name}")
        perturbation = value["perturbations"][name]
        _require_exact_fields(perturbation, PERTURBATION_FIELDS, f"{name} perturbation")
        if perturbation["distribution"] != "uniform_delta":
            raise ContractError(f"{name} distribution must be uniform_delta")
        _require_vector(perturbation["half_width"], f"{name} half_width", nonnegative=True)

    tolerances = value["tolerances"]
    _require_exact_fields(tolerances, TOLERANCE_FIELDS, "tolerances")
    if any(not _is_finite_real(tolerances[name]) or tolerances[name] <= 0
           for name in TOLERANCE_FIELDS):
        raise ContractError("tolerances must be positive finite real values")


def validate_result(value):
    _require_exact_fields(value, RESULT_FIELDS, "result")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ContractError("unsupported result schema")
    for name in ("scenario_id", "solver", "solver_status"):
        _require_nonempty_string(value[name], name)
    sample_id = value["sample_id"]
    if not isinstance(sample_id, int) or isinstance(sample_id, bool) or sample_id < 0:
        raise ContractError("sample_id must be a nonnegative integer")

    _require_exact_fields(value["input"], VECTOR_FIELDS, "result input")
    for name in VECTOR_FIELDS:
        _require_vector(value["input"][name], f"result input {name}")

    classification = value["classification"]
    success = value["success"]
    if not isinstance(classification, str) or classification not in CLASSIFICATIONS:
        raise ContractError("unsupported result classification")
    if not isinstance(success, bool):
        raise ContractError("success must be a boolean")
    if success != (classification == "success"):
        raise ContractError("success and classification must agree")
    error_type = value["error_type"]
    if error_type not in ERROR_TYPES:
        raise ContractError("unsupported result error_type")
    if (classification == "solver_error") != (error_type != "none"):
        raise ContractError("error_type must be set only for solver_error")

    metrics = value["metrics"]
    _require_mapping(metrics, "metrics")
    if any(not _is_finite_real(metric) for metric in metrics.values()):
        raise ContractError("metrics values must be finite real scalars")

    provenance = value["provenance"]
    _require_exact_fields(provenance, PROVENANCE_FIELDS, "provenance")
    digest = provenance["manifest_sha256"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        raise ContractError("manifest_sha256 must contain 64 hexadecimal characters")
    for name in PROVENANCE_FIELDS - {"manifest_sha256"}:
        _require_nonempty_string(provenance[name], f"provenance {name}")
