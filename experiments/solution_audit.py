"""求解轨迹的独立数值质量审计。"""

import numpy as np

from MarsLanding import mars_params as p


def classify_metrics(status, metrics, tolerances):
    """结合求解器状态和逐项容差给出审计结论。"""
    if status in {"infeasible", "infeasible_inaccurate"}:
        return "solver_infeasible"
    if status != "optimal":
        return "solver_error"
    limits = {
        "terminal_position_m": "terminal_m",
        "terminal_velocity_mps": "terminal_mps",
        "max_dynamics_residual": "dynamics",
        "max_cone_violation": "cone",
        "mass_bound_violation_kg": "mass_kg",
    }
    try:
        within_tolerance = all(
            np.isscalar(metrics[metric])
            and np.isfinite(float(metrics[metric]))
            and abs(float(metrics[metric])) <= tolerances[tolerance]
            for metric, tolerance in limits.items()
        ) and set(metrics) == set(limits) and set(tolerances) == set(limits.values())
    except (KeyError, TypeError, ValueError):
        within_tolerance = False
    return "success" if within_tolerance else "physical_violation"


def compute_metrics(solution):
    """从完整轨迹重算各组等式残差和不等式违反量。"""
    r = np.asarray(solution["r"], dtype=float)
    v = np.asarray(solution["v"], dtype=float)
    z = np.asarray(solution["z"], dtype=float)
    u = np.asarray(solution["u"], dtype=float)
    sigma = np.asarray(solution["sigma"], dtype=float)
    expected = {
        "r": (p.N + 1, 3), "v": (p.N + 1, 3), "z": (p.N + 1,),
        "u": (p.N + 1, 3), "sigma": (p.N + 1,),
    }
    for name, value in {"r": r, "v": v, "z": z, "u": u, "sigma": sigma}.items():
        if value.shape != expected[name]:
            raise ValueError(f"{name} must have shape {expected[name]}, got {value.shape}")

    pos = r[1:] - r[:-1] - v[:-1] * p.dt - 0.5 * u[:-1] * p.dt**2 + 0.5 * p.gv * p.dt**2
    vel = v[1:] - v[:-1] - u[:-1] * p.dt + p.gv * p.dt
    mass_dyn = z[1:] - z[:-1] + p.alpha * sigma[:-1] * p.dt
    glide = np.linalg.norm(r[:, 1:3], axis=1) - r[:, 0] * np.tan(p.theta)
    thrust = np.linalg.norm(u, axis=1) - sigma

    mass = np.exp(z)
    dynamics = max(
        np.max(np.linalg.norm(pos, axis=1)),
        np.max(np.linalg.norm(vel, axis=1)),
        np.max(np.abs(mass_dyn)),
    )
    cone = max(
        np.max(np.maximum(glide, 0.0)),
        np.max(np.maximum(thrust, 0.0)),
    )
    mass_bounds = max(
        np.max(np.maximum(p.m_dry - mass, 0.0)),
        np.max(np.maximum(mass - p.m0, 0.0)),
    )

    return {
        "terminal_position_m": float(np.linalg.norm(r[-1] - p.rf)),
        "terminal_velocity_mps": float(np.linalg.norm(v[-1] - p.vf)),
        "max_dynamics_residual": float(dynamics),
        "max_cone_violation": float(cone),
        "mass_bound_violation_kg": float(mass_bounds),
    }
