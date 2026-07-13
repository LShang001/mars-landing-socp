"""Stage B1 干重可行的参数化固定终端时间 SOCP。

该模型与 ``legacy_tf81_v1`` 并列存在，不生成或替换手写矩阵实现。
"""

from dataclasses import dataclass, field
import math

import cvxpy as cp
import numpy as np

from MarsLanding import mars_params as legacy

_DEFAULT_R0 = tuple(float(x) for x in legacy.r0)
_DEFAULT_V0 = tuple(float(x) for x in legacy.v0)
_DEFAULT_RF = tuple(float(x) for x in legacy.rf)
_DEFAULT_VF = tuple(float(x) for x in legacy.vf)


@dataclass(frozen=True)
class PhysicalModelConfig:
    N: int
    tf_s: float
    model_id: str = "physical_free_tf_v1"
    legacy_reference: str = "legacy_tf81_v1"
    g_mps2: float = float(legacy.g_mars)
    m0_kg: float = float(legacy.m0)
    m_dry_kg: float = float(legacy.m_dry)
    alpha: float = float(legacy.alpha)
    rho_min_n: float = float(legacy.rho1)
    rho_max_n: float = float(legacy.rho2)
    theta_rad: float = float(legacy.theta)
    r0_m: tuple = field(default_factory=lambda: _DEFAULT_R0)
    v0_mps: tuple = field(default_factory=lambda: _DEFAULT_V0)
    rf_m: tuple = field(default_factory=lambda: _DEFAULT_RF)
    vf_mps: tuple = field(default_factory=lambda: _DEFAULT_VF)

    def __post_init__(self):
        if type(self.N) is not int or self.N < 2:
            raise ValueError("N must be an integer >= 2")
        scalar_fields = (
            self.tf_s, self.g_mps2, self.m0_kg, self.m_dry_kg, self.alpha,
            self.rho_min_n, self.rho_max_n, self.theta_rad,
        )
        if any(isinstance(x, bool) or not isinstance(x, (int, float))
               or not math.isfinite(x) or x <= 0 for x in scalar_fields):
            raise ValueError("physical scalar parameters must be positive finite numbers")
        if self.m0_kg <= self.m_dry_kg or self.rho_max_n <= self.rho_min_n:
            raise ValueError("mass and thrust bounds must be strictly ordered")
        if not 0 < self.theta_rad < math.pi / 2:
            raise ValueError("theta_rad must lie strictly between zero and pi/2")
        for name in ("r0_m", "v0_mps", "rf_m", "vf_mps"):
            value = getattr(self, name)
            try:
                normalized = tuple(float(x) for x in value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{name} must contain three finite values") from error
            if len(normalized) != 3 or any(not math.isfinite(x) for x in normalized):
                raise ValueError(f"{name} must contain three finite values")
            object.__setattr__(self, name, normalized)
        if self.model_id != "physical_free_tf_v1":
            raise ValueError("model_id must identify physical_free_tf_v1")
        if self.legacy_reference != "legacy_tf81_v1":
            raise ValueError("legacy_reference must identify legacy_tf81_v1")

    @property
    def dt_s(self):
        return float(self.tf_s) / self.N


@dataclass(frozen=True)
class BuiltProblem:
    problem: cp.Problem
    variables: dict
    control_intervals: int
    objective_scale_s: float


@dataclass(frozen=True)
class FixedTimeResult:
    model_id: str
    legacy_reference: str
    N: int
    tf_s: float
    dt_s: float
    solver: str
    solver_status: str
    classification: str
    num_iters: int | None = None
    objective_value: float | None = None
    fuel_kg: float | None = None
    terminal_mass_kg: float | None = None
    r: np.ndarray | None = None
    v: np.ndarray | None = None
    z: np.ndarray | None = None
    u: np.ndarray | None = None
    sigma: np.ndarray | None = None
    error: str = ""


def _reference_terms(config, k):
    elapsed = k * config.dt_s
    reference_mass = config.m0_kg - config.alpha * config.rho_max_n * elapsed
    if reference_mass <= 0:
        raise ValueError("reference mass must remain positive over the mesh")
    z_ref = math.log(reference_mass)
    return (
        z_ref,
        config.rho_min_n * math.exp(-z_ref),
        config.rho_max_n * math.exp(-z_ref),
    )


def build_fixed_time_problem(config):
    """构造固定 ``(N, tf)`` 的凸内层问题。"""
    if not isinstance(config, PhysicalModelConfig):
        raise TypeError("config must be a PhysicalModelConfig")
    N, dt = config.N, config.dt_s
    r = cp.Variable((N + 1, 3), name="r")
    v = cp.Variable((N + 1, 3), name="v")
    z = cp.Variable(N + 1, name="z")
    u = cp.Variable((N, 3), name="u")
    sigma = cp.Variable(N, name="sigma")
    gravity = np.array([config.g_mps2, 0.0, 0.0])

    constraints = [
        r[0] == np.asarray(config.r0_m), v[0] == np.asarray(config.v0_mps),
        z[0] == math.log(config.m0_kg), r[N] == np.asarray(config.rf_m),
        v[N] == np.asarray(config.vf_mps),
    ]
    for k in range(N):
        constraints.extend([
            r[k + 1] == r[k] + v[k] * dt + 0.5 * u[k] * dt**2
            - 0.5 * gravity * dt**2,
            v[k + 1] == v[k] + u[k] * dt - gravity * dt,
            z[k + 1] == z[k] - config.alpha * sigma[k] * dt,
        ])
        z_ref, mu_min, mu_max = _reference_terms(config, k)
        constraints.extend([
            mu_min * (z[k] - z_ref - 1.0) + sigma[k] >= 0,
            mu_max * (z[k] - z_ref - 1.0) + sigma[k] <= 0,
            cp.SOC(sigma[k], u[k]),
        ])

    for k in range(N + 1):
        elapsed = k * dt
        reachable_min_mass = config.m0_kg - config.alpha * config.rho_max_n * elapsed
        reachable_max_mass = config.m0_kg - config.alpha * config.rho_min_n * elapsed
        if reachable_max_mass <= 0:
            raise ValueError("mass envelope must remain positive over the mesh")
        constraints.extend([
            z[k] >= math.log(config.m_dry_kg),
            z[k] >= math.log(max(config.m_dry_kg, reachable_min_mass)),
            z[k] <= math.log(reachable_max_mass),
            z[k] <= math.log(config.m0_kg),
            cp.SOC(r[k, 0] * math.tan(config.theta_rad), r[k, 1:3]),
        ])

    problem = cp.Problem(cp.Minimize(cp.sum(sigma) * dt), constraints)
    return BuiltProblem(
        problem=problem,
        variables={"r": r, "v": v, "z": z, "u": u, "sigma": sigma},
        control_intervals=N,
        objective_scale_s=dt,
    )


def _empty_result(config, solver, status, classification, error=""):
    return FixedTimeResult(
        model_id=config.model_id, legacy_reference=config.legacy_reference,
        N=config.N, tf_s=float(config.tf_s), dt_s=config.dt_s,
        solver=solver, solver_status=status, classification=classification, error=error,
    )


def classify_solver_status(status):
    """将求解器状态映射到互斥证据分类。"""
    status = str(status)
    if status == cp.OPTIMAL:
        return "success"
    if status == cp.INFEASIBLE:
        return "solver_infeasible"
    if "inaccurate" in status:
        return "solver_inaccurate"
    return "solver_error"


def _extract_optimal_values(config, built):
    expected_shapes = {
        "r": (config.N + 1, 3), "v": (config.N + 1, 3),
        "z": (config.N + 1,), "u": (config.N, 3), "sigma": (config.N,),
    }
    values = {}
    for name, shape in expected_shapes.items():
        raw = built.variables[name].value
        if raw is None:
            raise ValueError(f"{name} has no value")
        value = np.asarray(raw, dtype=float)
        if value.shape != shape or not np.all(np.isfinite(value)):
            raise ValueError(f"{name} must have finite shape {shape}")
        values[name] = value
    objective = float(built.problem.value)
    if not math.isfinite(objective):
        raise ValueError("objective must be finite")
    terminal_mass = math.exp(float(values["z"][-1]))
    if not math.isfinite(terminal_mass):
        raise ValueError("terminal mass must be finite")
    return values, objective, terminal_mass


def solve_fixed_time(config, solver_name):
    """调用 ECOS 或 Clarabel；失败类别不做物理含义替换。"""
    canonical = {"ECOS": cp.ECOS, "Clarabel": cp.CLARABEL}
    if solver_name not in canonical:
        return _empty_result(
            config, str(solver_name), "not_run", "solver_error",
            f"unsupported solver: {solver_name}",
        )
    try:
        built = build_fixed_time_problem(config)
        built.problem.solve(solver=canonical[solver_name], verbose=False)
    except Exception as error:
        return _empty_result(
            config, solver_name, "exception", "solver_error",
            f"{type(error).__name__}: {error}",
        )

    status = str(built.problem.status)
    classification = classify_solver_status(status)
    if classification != "success":
        return _empty_result(config, solver_name, status, classification)
    try:
        values, objective, terminal_mass = _extract_optimal_values(config, built)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return _empty_result(
            config, solver_name, status, "solver_error",
            f"invalid optimal solution: {type(error).__name__}: {error}",
        )
    stats = built.problem.solver_stats
    return FixedTimeResult(
        model_id=config.model_id, legacy_reference=config.legacy_reference,
        N=config.N, tf_s=float(config.tf_s), dt_s=config.dt_s,
        solver=solver_name, solver_status=status, classification="success",
        num_iters=int(stats.num_iters) if stats.num_iters is not None else None,
        objective_value=objective,
        fuel_kg=config.m0_kg - terminal_mass, terminal_mass_kg=terminal_mass,
        r=values["r"], v=values["v"], z=values["z"],
        u=values["u"], sigma=values["sigma"],
    )
