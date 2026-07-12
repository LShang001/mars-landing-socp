import unittest
from pathlib import Path
import tempfile

from experiments.scenario_loader import load_scenario, sample_inputs


class ScenarioLoaderTests(unittest.TestCase):
    def test_manifest_is_deterministic(self):
        path = Path("experiments/scenarios/near_nominal_v1.json")
        first, first_hash = load_scenario(path)
        second, second_hash = load_scenario(path)
        self.assertEqual(first, second)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 64)

    def test_samples_are_reproducible_and_keep_symmetry(self):
        scenario, _ = load_scenario(Path("experiments/scenarios/near_nominal_v1.json"))
        samples = sample_inputs(scenario, count=2)
        self.assertEqual(samples, sample_inputs(scenario, count=2))
        self.assertEqual(samples[0]["r0_m"][1], 0.0)
        self.assertEqual(samples[0]["v0_mps"][1], 0.0)

    def test_rejects_non_integer_count(self):
        scenario, _ = load_scenario(Path("experiments/scenarios/near_nominal_v1.json"))
        for count in (2.5, True):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "count must be a positive integer"):
                    sample_inputs(scenario, count=count)

    def test_manifest_hash_and_first_two_samples_are_fixed(self):
        scenario, digest = load_scenario(Path("experiments/scenarios/near_nominal_v1.json"))
        self.assertEqual(digest, "c985c50f262eec4fbb6afdeda589cf2f38839c3fc90153430700f9fd56c14a76")
        self.assertEqual(sample_inputs(scenario, count=2), [
            {"sample_id": 0, "r0_m": [1449.816047538945, 0.0, 2092.797576724562],
             "v0_mps": [-71.05366063211854, 0.0, 86.2397808134481]},
            {"sample_id": 1, "r0_m": [1323.2334448672798, 0.0, 2040.4460046972836],
             "v0_mps": [-66.67709688815819, 0.0, 118.79639408647978]},
        ])

    def test_count_boundaries(self):
        scenario, _ = load_scenario(Path("experiments/scenarios/near_nominal_v1.json"))
        self.assertEqual(len(sample_inputs(scenario)), scenario["sample_count"])
        for count in (0, scenario["sample_count"] + 1):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "manifest sample_count"):
                    sample_inputs(scenario, count=count)

    def test_loader_rejects_non_finite_constants_and_non_object_root(self):
        for content in ('{"value": NaN}', '{"value": Infinity}', '[]', 'null', '{'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "scenario.json"
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_scenario(path)


if __name__ == "__main__":
    unittest.main()
