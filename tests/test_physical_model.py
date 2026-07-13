import unittest
from unittest import mock
from dataclasses import replace

import numpy as np


class PhysicalModelTests(unittest.TestCase):
    def test_default_config_is_distinct_from_legacy_and_immutable(self):
        from experiments.physical_model import PhysicalModelConfig

        config = PhysicalModelConfig(N=30, tf_s=78.4)
        self.assertEqual(config.model_id, "physical_free_tf_v1")
        self.assertEqual(config.legacy_reference, "legacy_tf81_v1")
        self.assertAlmostEqual(config.dt_s, 78.4 / 30)
        with self.assertRaisesRegex(Exception, "cannot assign"):
            config.N = 40

    def test_config_rejects_invalid_dimensions_and_physics(self):
        from experiments.physical_model import PhysicalModelConfig

        for kwargs in ({"N": True}, {"N": 1}, {"tf_s": 0}, {"tf_s": np.inf},
                       {"m0_kg": 1500, "m_dry_kg": 1505},
                       {"r0_m": (1.0, 2.0)}, {"theta_rad": np.pi}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PhysicalModelConfig(**({"N": 30, "tf_s": 78.4} | kwargs))

    def test_config_copies_vectors_and_isolated_defaults(self):
        from MarsLanding import mars_params as legacy
        from experiments.physical_model import PhysicalModelConfig

        source = np.array([1500.0, 0.0, 2000.0])
        config = PhysicalModelConfig(N=30, tf_s=78.4, r0_m=source)
        source[0] = -1.0
        self.assertEqual(config.r0_m, (1500.0, 0.0, 2000.0))
        old = legacy.r0.copy()
        try:
            legacy.r0[0] = -99.0
            fresh = PhysicalModelConfig(N=30, tf_s=78.4)
            self.assertEqual(fresh.r0_m, (1500.0, 0.0, 2000.0))
        finally:
            legacy.r0[:] = old

    def test_builder_uses_node_states_and_interval_controls(self):
        from experiments.physical_model import PhysicalModelConfig, build_fixed_time_problem

        built = build_fixed_time_problem(PhysicalModelConfig(N=4, tf_s=8.0))
        self.assertEqual(built.variables["r"].shape, (5, 3))
        self.assertEqual(built.variables["v"].shape, (5, 3))
        self.assertEqual(built.variables["z"].shape, (5,))
        self.assertEqual(built.variables["u"].shape, (4, 3))
        self.assertEqual(built.variables["sigma"].shape, (4,))
        self.assertEqual(built.control_intervals, 4)
        self.assertAlmostEqual(built.objective_scale_s, 2.0)

    def test_build_and_solve_do_not_mutate_legacy_parameters(self):
        from MarsLanding import mars_params as legacy
        from experiments.physical_model import PhysicalModelConfig, build_fixed_time_problem

        snapshot = (legacy.N, legacy.t_f, legacy.dt, legacy.r0.copy(), legacy.v0.copy())
        build_fixed_time_problem(PhysicalModelConfig(N=12, tf_s=77.0))
        self.assertEqual((legacy.N, legacy.t_f, legacy.dt), snapshot[:3])
        np.testing.assert_array_equal(legacy.r0, snapshot[3])
        np.testing.assert_array_equal(legacy.v0, snapshot[4])

    def test_known_candidate_is_dry_mass_feasible_and_cross_solver_consistent(self):
        from experiments.physical_model import PhysicalModelConfig, solve_fixed_time

        config = PhysicalModelConfig(N=30, tf_s=78.4)
        ecos = solve_fixed_time(config, "ECOS")
        clarabel = solve_fixed_time(config, "Clarabel")
        self.assertEqual(ecos.classification, "success")
        self.assertEqual(clarabel.classification, "success")
        self.assertGreaterEqual(ecos.terminal_mass_kg, config.m_dry_kg - 1e-3)
        self.assertGreaterEqual(clarabel.terminal_mass_kg, config.m_dry_kg - 1e-3)
        self.assertAlmostEqual(ecos.fuel_kg, clarabel.fuel_kg, delta=0.02)
        self.assertEqual(ecos.u.shape, (30, 3))
        self.assertEqual(ecos.z.shape, (31,))
        self.assertAlmostEqual(
            ecos.objective_value, float(np.sum(ecos.sigma) * config.dt_s), delta=1e-7
        )

    def test_legacy_tf81_cannot_return_an_optimal_below_dry_mass_trajectory(self):
        from experiments.physical_model import PhysicalModelConfig, solve_fixed_time

        config = PhysicalModelConfig(N=30, tf_s=81.0)
        result = solve_fixed_time(config, "ECOS")
        if result.classification == "success":
            self.assertGreaterEqual(result.terminal_mass_kg, config.m_dry_kg - 1e-3)
        else:
            self.assertIn(result.classification, {"solver_infeasible", "solver_inaccurate"})

    def test_unknown_solver_is_error_not_infeasible(self):
        from experiments.physical_model import PhysicalModelConfig, solve_fixed_time

        result = solve_fixed_time(PhysicalModelConfig(N=4, tf_s=8.0), "unknown")
        self.assertEqual(result.classification, "solver_error")
        self.assertNotEqual(result.classification, "solver_infeasible")
        self.assertIn("unsupported solver", result.error)

    def test_inaccurate_status_is_never_reported_as_infeasible(self):
        from experiments.physical_model import classify_solver_status

        self.assertEqual(classify_solver_status("infeasible"), "solver_infeasible")
        self.assertEqual(
            classify_solver_status("infeasible_inaccurate"), "solver_inaccurate"
        )
        self.assertEqual(classify_solver_status("optimal_inaccurate"), "solver_inaccurate")

    def test_invalid_optimal_vector_becomes_structured_solver_error(self):
        from experiments.physical_model import PhysicalModelConfig, solve_fixed_time

        class FakeStats:
            num_iters = 1

        class FakeProblem:
            status = "optimal"
            value = 1.0
            solver_stats = FakeStats()

            def solve(self, **kwargs):
                return None

        class FakeVariable:
            def __init__(self, value):
                self.value = value

        fake = mock.Mock(
            problem=FakeProblem(),
            variables={
                "r": FakeVariable(None), "v": FakeVariable(np.zeros((5, 3))),
                "z": FakeVariable(np.zeros(5)), "u": FakeVariable(np.zeros((4, 3))),
                "sigma": FakeVariable(np.zeros(4)),
            },
        )
        with mock.patch("experiments.physical_model.build_fixed_time_problem", return_value=fake):
            result = solve_fixed_time(PhysicalModelConfig(N=4, tf_s=8.0), "ECOS")
        self.assertEqual(result.classification, "solver_error")
        self.assertIn("invalid optimal solution", result.error)

    def test_audit_recomputes_node_and_dense_interval_metrics(self):
        from experiments.physical_model import (
            PhysicalModelConfig, audit_fixed_time_result, solve_fixed_time,
        )

        config = PhysicalModelConfig(N=30, tf_s=78.4)
        result = solve_fixed_time(config, "ECOS")
        metrics = audit_fixed_time_result(config, result, dense_samples_per_interval=5)
        self.assertEqual(set(metrics), {
            "terminal_position_m", "terminal_velocity_mps", "dynamics_residual",
            "soc_violation", "mass_violation_kg", "thrust_envelope_violation",
            "fuel_consistency_kg", "dense_path_violation",
        })
        self.assertTrue(all(np.isscalar(value) and np.isfinite(value)
                            and value >= 0 for value in metrics.values()))
        self.assertLess(metrics["terminal_position_m"], 1e-3)
        self.assertLess(metrics["terminal_velocity_mps"], 1e-3)
        self.assertLess(metrics["dynamics_residual"], 1e-5)
        self.assertLess(metrics["mass_violation_kg"], 1e-3)
        self.assertLess(metrics["fuel_consistency_kg"], 1e-3)

    def test_audit_detects_injected_dynamics_cone_and_mass_violations(self):
        from experiments.physical_model import (
            PhysicalModelConfig, audit_fixed_time_result, solve_fixed_time,
        )

        config = PhysicalModelConfig(N=30, tf_s=78.4)
        result = solve_fixed_time(config, "ECOS")
        r, z, u = result.r.copy(), result.z.copy(), result.u.copy()
        r[4, 0] += 2.0
        z[5] = np.log(config.m_dry_kg - 3.0)
        u[6] *= 100.0
        metrics = audit_fixed_time_result(
            config, replace(result, r=r, z=z, u=u), dense_samples_per_interval=3
        )
        self.assertGreater(metrics["dynamics_residual"], 1.0)
        self.assertGreater(metrics["mass_violation_kg"], 2.9)
        self.assertGreater(metrics["soc_violation"], 0.0)

    def test_audit_rejects_wrong_shapes_and_nonoptimal_results(self):
        from experiments.physical_model import (
            PhysicalModelConfig, audit_fixed_time_result, solve_fixed_time,
        )

        config = PhysicalModelConfig(N=30, tf_s=81.0)
        nonoptimal = solve_fixed_time(config, "ECOS")
        with self.assertRaisesRegex(ValueError, "successful optimal"):
            audit_fixed_time_result(config, nonoptimal)

        good_config = PhysicalModelConfig(N=30, tf_s=78.4)
        good = solve_fixed_time(good_config, "ECOS")
        with self.assertRaisesRegex(ValueError, "shape"):
            audit_fixed_time_result(good_config, replace(good, sigma=good.sigma[:-1]))

    def test_audit_classification_uses_exact_metric_contract(self):
        from experiments.physical_model import classify_audit_metrics

        tolerances = {
            "terminal_position_m": 1e-3, "terminal_velocity_mps": 1e-3,
            "dynamics_residual": 1e-5, "soc_violation": 1e-5,
            "mass_violation_kg": 1e-3, "thrust_envelope_violation": 1e-5,
            "fuel_consistency_kg": 1e-3, "dense_path_violation": 1e-3,
        }
        metrics = {name: 0.0 for name in tolerances}
        self.assertEqual(classify_audit_metrics("success", metrics, tolerances), "success")
        metrics["dense_path_violation"] = 2e-3
        self.assertEqual(
            classify_audit_metrics("success", metrics, tolerances), "physical_violation"
        )
        self.assertEqual(classify_audit_metrics("solver_inaccurate", {}, tolerances),
                         "solver_inaccurate")


if __name__ == "__main__":
    unittest.main()
