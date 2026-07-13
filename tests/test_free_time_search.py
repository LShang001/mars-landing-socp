import unittest
from decimal import Decimal


class FreeTimeSearchTests(unittest.TestCase):
    def test_decimal_grid_is_sorted_unique_and_endpoint_inclusive(self):
        from experiments.free_time_search import decimal_grid
        self.assertEqual(decimal_grid("75.00", "76.00", "0.50"),
                         [Decimal("75.00"), Decimal("75.50"), Decimal("76.00")])

    def test_search_refines_each_mesh_independently_and_preserves_failures(self):
        from experiments.free_time_search import search_mesh

        calls = []
        def fake_solve(N, tf):
            calls.append((N, tf))
            if tf == Decimal("76.00"):
                return {"classification": "solver_error", "fuel_kg": None}
            return {"classification": "success", "fuel_kg": float((tf-Decimal("75.5"))**2)+N}

        records = search_mesh(20, "75.00", "76.00", ["0.50", "0.10"], fake_solve)
        self.assertTrue(any(r["classification"] == "solver_error" for r in records))
        self.assertEqual(len({r["candidate_id"] for r in records}), len(records))
        self.assertTrue(all(r["N"] == 20 for r in records))
        self.assertIn((20, Decimal("75.50")), calls)
        self.assertIn((20, Decimal("75.40")), calls)
        self.assertIn((20, Decimal("75.60")), calls)

    def test_exception_is_solver_error_not_infeasible(self):
        from experiments.free_time_search import search_mesh
        def broken(N, tf):
            raise RuntimeError("boom")
        records = search_mesh(20, "75.00", "75.50", ["0.50"], broken)
        self.assertEqual({r["classification"] for r in records}, {"solver_error"})
        self.assertTrue(all(r["error_type"] == "RuntimeError" for r in records))


if __name__ == "__main__":
    unittest.main()
