"""Stage B1 研究 manifest 的严格契约。"""

import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path


STUDY_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "model_id",
        "legacy_reference",
        "handwritten_asset",
        "provenance",
        "meshes",
        "terminal_time_search",
        "solvers",
        "tolerances",
    }
)
PROVENANCE_FIELDS = frozenset(
    {"protocol_version", "parameter_source", "implementation_plan", "design_spec"}
)
SEARCH_FIELDS = frozenset({"lower_s", "upper_s", "levels"})
LEVEL_FIELDS = frozenset({"step_s"})
SOLVER_FIELDS = frozenset({"name", "role"})
TOLERANCE_FIELDS = frozenset({"audit", "cross_solver", "convergence"})
AUDIT_FIELDS = frozenset(
    {
        "terminal_position_m",
        "terminal_velocity_mps",
        "dynamics_residual",
        "soc_violation",
        "mass_violation_kg",
        "thrust_envelope_violation",
        "fuel_consistency_kg",
        "dense_path_violation",
    }
)
CROSS_SOLVER_FIELDS = frozenset(
    {"fuel_kg", "terminal_mass_kg", "audit_residual"}
)
CONVERGENCE_FIELDS = frozenset(
    {"fuel_change_kg", "tf_change_s", "consecutive_meshes"}
)

EXPECTED_IDENTITIES = {
    "study_id": "free_time_mesh_v1",
    "model_id": "physical_free_tf_v1",
    "legacy_reference": "legacy_tf81_v1",
    "handwritten_asset": "MarsLanding/MarsLanding.c",
}
EXPECTED_MESHES = [20, 30, 40, 60]
EXPECTED_LOWER_S = Decimal("75.00")
EXPECTED_UPPER_S = Decimal("82.00")
EXPECTED_LEVEL_STEPS = [Decimal("0.50"), Decimal("0.10"), Decimal("0.02")]
EXPECTED_SOLVERS = [
    {"name": "ECOS", "role": "complete_search"},
    {"name": "Clarabel", "role": "confirmation"},
]
EXPECTED_PROVENANCE = {
    "protocol_version": "stage_b1_v1",
    "parameter_source": "MarsLanding/mars_params.py",
    "implementation_plan": "docs/superpowers/plans/2026-07-13-stage-b1-free-time-mesh.md",
    "design_spec": "docs/superpowers/specs/2026-07-13-stage-b1-free-time-mesh-design.md",
}
EXPECTED_TOLERANCES = {
    "audit": {
        "terminal_position_m": 0.001,
        "terminal_velocity_mps": 0.0001,
        "dynamics_residual": 0.000001,
        "soc_violation": 0.000001,
        "mass_violation_kg": 0.001,
        "thrust_envelope_violation": 0.000001,
        "fuel_consistency_kg": 0.001,
        "dense_path_violation": 0.0001,
    },
    "cross_solver": {
        "fuel_kg": 0.01,
        "terminal_mass_kg": 0.01,
        "audit_residual": 0.00001,
    },
    "convergence": {
        "fuel_change_kg": 0.1,
        "tf_change_s": 0.05,
        "consecutive_meshes": 3,
    },
}


def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _require_exact_fields(value, fields, label):
    _require_mapping(value, label)
    actual = set(value)
    missing = fields - actual
    unknown = actual - fields
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{label} unknown fields: {sorted(unknown)}")


def _decimal_string(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must define a decimal grid as a string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{label} must define a valid decimal grid") from error
    if not result.is_finite():
        raise ValueError(f"{label} must define a finite decimal grid")
    return result


def _is_integral(value):
    return value == value.to_integral_value()


def _validate_search(search):
    _require_exact_fields(search, SEARCH_FIELDS, "terminal_time_search")
    lower = _decimal_string(search["lower_s"], "terminal_time_search lower_s")
    upper = _decimal_string(search["upper_s"], "terminal_time_search upper_s")
    if lower != EXPECTED_LOWER_S or upper != EXPECTED_UPPER_S or lower >= upper:
        raise ValueError("terminal_time_search must use the fixed [75.00, 82.00] interval")

    levels = search["levels"]
    if not isinstance(levels, list) or len(levels) < 2:
        raise ValueError("terminal_time_search levels must contain coarse-to-fine grids")
    steps = []
    for index, level in enumerate(levels):
        _require_exact_fields(level, LEVEL_FIELDS, f"terminal_time_search level {index}")
        step = _decimal_string(
            level["step_s"], f"terminal_time_search level {index} step_s"
        )
        if step <= 0:
            raise ValueError("terminal_time_search decimal grid steps must be positive")
        steps.append(step)

    if not _is_integral((upper - lower) / steps[0]):
        raise ValueError("terminal_time_search coarse decimal grid must cover the interval")
    for coarse, fine in zip(steps, steps[1:]):
        if fine >= coarse or not _is_integral(coarse / fine):
            raise ValueError(
                "terminal_time_search levels must be nested decimal grids and match "
                "the pre-registered v1 levels"
            )
    if steps != EXPECTED_LEVEL_STEPS:
        raise ValueError("terminal_time_search must use the pre-registered v1 levels")


def _validate_solvers(solvers):
    if not isinstance(solvers, list):
        raise ValueError("solvers must be a list")
    for index, solver in enumerate(solvers):
        _require_exact_fields(solver, SOLVER_FIELDS, f"solver {index}")
    names = [solver["name"] for solver in solvers]
    if len(names) != len(set(names)):
        raise ValueError("solver names must be unique")
    if solvers != EXPECTED_SOLVERS:
        raise ValueError("solvers must assign ECOS complete search and Clarabel confirmation")


def _positive_finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")


def _validate_tolerance_section(section, fields, label):
    _require_exact_fields(section, fields, label)
    for name, value in section.items():
        _positive_finite(value, f"{label} {name}")


def _validate_tolerances(tolerances):
    _require_exact_fields(tolerances, TOLERANCE_FIELDS, "tolerances")
    _validate_tolerance_section(tolerances["audit"], AUDIT_FIELDS, "audit tolerances")
    _validate_tolerance_section(
        tolerances["cross_solver"], CROSS_SOLVER_FIELDS, "cross_solver tolerances"
    )
    _validate_tolerance_section(
        tolerances["convergence"], CONVERGENCE_FIELDS, "convergence tolerances"
    )
    if type(tolerances["convergence"]["consecutive_meshes"]) is not int:
        raise ValueError("convergence consecutive_meshes must be a positive finite integer")
    if tolerances["convergence"]["consecutive_meshes"] != 3:
        raise ValueError(
            "convergence consecutive_meshes must equal the pre-registered value 3"
        )
    if tolerances != EXPECTED_TOLERANCES:
        raise ValueError("tolerances must equal the pre-registered v1 values")


def _validate_provenance(provenance):
    _require_exact_fields(provenance, PROVENANCE_FIELDS, "provenance")
    if provenance != EXPECTED_PROVENANCE:
        raise ValueError("provenance must equal the pre-registered repository sources")


def validate_study_manifest(manifest):
    """校验并返回 Stage B1 manifest，不接受未知字段或隐式类型转换。"""
    _require_exact_fields(manifest, STUDY_FIELDS, "study manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("schema_version must equal integer 1")
    for field, expected in EXPECTED_IDENTITIES.items():
        if manifest[field] != expected:
            raise ValueError(f"{field} must equal {expected}")

    meshes = manifest["meshes"]
    if (
        not isinstance(meshes, list)
        or any(type(mesh) is not int for mesh in meshes)
        or any(left >= right for left, right in zip(meshes, meshes[1:]))
        or meshes != EXPECTED_MESHES
    ):
        raise ValueError("meshes must be exactly [20, 30, 40, 60] strictly increasing integers")

    _validate_search(manifest["terminal_time_search"])
    _validate_solvers(manifest["solvers"])
    _validate_tolerances(manifest["tolerances"])
    _validate_provenance(manifest["provenance"])
    return manifest


def _reject_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_study_manifest(path):
    """从 JSON 文件加载并严格校验 Stage B1 manifest。"""
    path = Path(path)
    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream, object_pairs_hook=_reject_duplicate_fields)
    return validate_study_manifest(manifest)
