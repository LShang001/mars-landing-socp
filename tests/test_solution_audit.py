import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MarsLanding"))


class SolutionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tolerances = {
            "terminal_m": 1e-3,
            "terminal_mps": 1e-3,
            "dynamics": 1e-6,
            "cone": 1e-6,
            "mass_kg": 1e-3,
        }

    def test_classify_metrics_optimal_success(self):
        from experiments.solution_audit import classify_metrics

        metrics = {
            "terminal_position_m": 5e-4,
            "terminal_velocity_mps": 5e-4,
            "max_dynamics_residual": 5e-7,
            "max_cone_violation": 5e-7,
            "mass_bound_violation_kg": 5e-4,
        }
        self.assertEqual(classify_metrics("optimal", metrics, self.tolerances), "success")

    def test_classify_metrics_optimal_cone_violation(self):
        from experiments.solution_audit import classify_metrics

        metrics = {
            "terminal_position_m": 0.0,
            "terminal_velocity_mps": 0.0,
            "max_dynamics_residual": 0.0,
            "max_cone_violation": 2e-6,
            "mass_bound_violation_kg": 0.0,
        }
        self.assertEqual(
            classify_metrics("optimal", metrics, self.tolerances), "physical_violation"
        )

    def test_classify_metrics_infeasible(self):
        from experiments.solution_audit import classify_metrics

        self.assertEqual(classify_metrics("infeasible", {}, self.tolerances), "solver_infeasible")

    def test_classify_metrics_solver_error(self):
        from experiments.solution_audit import classify_metrics

        self.assertEqual(classify_metrics("solver_error", {}, self.tolerances), "solver_error")
        self.assertEqual(classify_metrics("optimal_inaccurate", {}, self.tolerances), "solver_error")

    def test_classify_metrics_non_scalar_is_physical_violation(self):
        from experiments.solution_audit import classify_metrics

        metrics = {
            "terminal_position_m": np.array([0.0]), "terminal_velocity_mps": 0.0,
            "max_dynamics_residual": 0.0, "max_cone_violation": 0.0,
            "mass_bound_violation_kg": 0.0,
        }
        self.assertEqual(classify_metrics("optimal", metrics, self.tolerances), "physical_violation")


    def test_compute_metrics_recomputes_all_model_residuals(self):
        from experiments.solution_audit import compute_metrics
        import mars_params as p

        u = np.zeros((p.N + 1, 3))
        sigma = np.full(p.N + 1, 0.01)
        r = np.zeros((p.N + 1, 3))
        v = np.zeros((p.N + 1, 3))
        z = np.zeros(p.N + 1)
        r[0], v[0], z[0] = p.r0, p.v0, np.log(p.m0)
        for k in range(p.N):
            r[k + 1] = r[k] + v[k] * p.dt + 0.5 * u[k] * p.dt**2 - 0.5 * p.gv * p.dt**2
            v[k + 1] = v[k] + u[k] * p.dt - p.gv * p.dt
            z[k + 1] = z[k] - p.alpha * sigma[k] * p.dt

        metrics = compute_metrics({"r": r, "v": v, "z": z, "u": u, "sigma": sigma})

        self.assertEqual(set(metrics), {
            "terminal_position_m", "terminal_velocity_mps", "max_dynamics_residual",
            "max_cone_violation", "mass_bound_violation_kg",
        })
        self.assertAlmostEqual(metrics["terminal_position_m"], np.linalg.norm(r[-1] - p.rf))
        self.assertAlmostEqual(metrics["terminal_velocity_mps"], np.linalg.norm(v[-1] - p.vf))
        self.assertAlmostEqual(metrics["max_dynamics_residual"], 0.0, delta=1e-9)
        expected_cone = np.maximum(
            np.linalg.norm(r[:, 1:3], axis=1) - r[:, 0] * np.tan(p.theta), 0
        ).max()
        self.assertAlmostEqual(metrics["max_cone_violation"], expected_cone)
        self.assertAlmostEqual(metrics["mass_bound_violation_kg"], 0.0)

        v[-1, 0] += 0.25
        self.assertAlmostEqual(compute_metrics(
            {"r": r, "v": v, "z": z, "u": u, "sigma": sigma}
        )["max_dynamics_residual"], 0.25)

        z[2] = np.log(p.m_dry - 3.0)
        self.assertAlmostEqual(compute_metrics(
            {"r": r, "v": v, "z": z, "u": u, "sigma": sigma}
        )["mass_bound_violation_kg"], 3.0)

    def test_compute_metrics_rejects_wrong_shapes(self):
        from experiments.solution_audit import compute_metrics
        import mars_params as p

        solution = {"r": np.zeros((p.N, 3)), "v": np.zeros((p.N + 1, 3)),
                    "z": np.zeros(p.N + 1), "u": np.zeros((p.N + 1, 3)),
                    "sigma": np.zeros(p.N + 1)}
        with self.assertRaisesRegex(ValueError, "r must have shape"):
            compute_metrics(solution)

    def test_nonoptimal_cvxpy_result_raises_status_before_value_access(self):
        from mars_solve import CvxpySolveError, _ensure_cvxpy_solution

        with self.assertRaises(CvxpySolveError) as caught:
            _ensure_cvxpy_solution(SimpleNamespace(status="infeasible"))
        self.assertEqual(caught.exception.status, "infeasible")
        with self.assertRaises(CvxpySolveError):
            _ensure_cvxpy_solution(SimpleNamespace(status="optimal_inaccurate"))


    def test_solve_cvxpy_return_full_preserves_default_api_and_exposes_trajectory(self):
        import cvxpy as cp
        import mars_params as p
        from mars_solve import solve_cvxpy

        fuel, label = solve_cvxpy(cp.ECOS)
        full_fuel, solution = solve_cvxpy(cp.ECOS, return_full=True)

        self.assertEqual(label, "CVXPY+ECOS")
        self.assertAlmostEqual(full_fuel, fuel, delta=1e-5)
        self.assertEqual(solution["r"].shape, (p.N + 1, 3))
        self.assertEqual(solution["v"].shape, (p.N + 1, 3))
        self.assertEqual(solution["z"].shape, (p.N + 1,))
        self.assertEqual(solution["u"].shape, (p.N + 1, 3))
        self.assertEqual(solution["sigma"].shape, (p.N + 1,))
        self.assertIn(solution["solver_status"], {cp.OPTIMAL, cp.OPTIMAL_INACCURATE})
        self.assertIsInstance(solution["num_iters"], int)

        from experiments.solution_audit import compute_metrics, classify_metrics
        metrics = compute_metrics(solution)
        self.assertAlmostEqual(metrics["mass_bound_violation_kg"], 0.7278765, delta=1e-4)
        self.assertEqual(classify_metrics(solution["solver_status"], metrics, self.tolerances),
                         "physical_violation")

    def test_solve_cvxpy_initial_state_override_does_not_mutate_globals(self):
        import cvxpy as cp
        import mars_solve

        original_r0 = mars_solve.r0.copy()
        original_v0 = mars_solve.v0.copy()
        mars_solve.solve_cvxpy(
            cp.ECOS, return_full=True,
            initial_r0=original_r0 + [1.0, 0.0, 0.0],
            initial_v0=original_v0 + [1.0, 0.0, 0.0],
        )
        np.testing.assert_array_equal(mars_solve.r0, original_r0)
        np.testing.assert_array_equal(mars_solve.v0, original_v0)


if __name__ == "__main__":
    unittest.main()
