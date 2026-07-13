import copy
import json
import math
import tempfile
import unittest
from pathlib import Path


MANIFEST_PATH = Path("experiments/studies/free_time_mesh_v1.json")
EXPECTED_PROVENANCE = {
    "protocol_version": "stage_b1_v1",
    "parameter_source": "MarsLanding/mars_params.py",
    "implementation_plan": "docs/superpowers/plans/2026-07-13-stage-b1-free-time-mesh.md",
    "design_spec": "docs/superpowers/specs/2026-07-13-stage-b1-free-time-mesh-design.md",
}


def load_json(path=MANIFEST_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


class StudyContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_json()

    def validate(self, manifest=None):
        from experiments.study_contracts import validate_study_manifest

        return validate_study_manifest(self.manifest if manifest is None else manifest)

    def test_versioned_manifest_is_valid_and_preserves_asset_boundary(self):
        validated = self.validate()
        self.assertEqual(validated["study_id"], "free_time_mesh_v1")
        self.assertEqual(validated["model_id"], "physical_free_tf_v1")
        self.assertEqual(validated["meshes"], [20, 30, 40, 60])
        self.assertEqual(validated["legacy_reference"], "legacy_tf81_v1")
        self.assertEqual(
            validated["handwritten_asset"], "MarsLanding/MarsLanding.c"
        )

    def test_loader_reads_and_validates_json(self):
        from experiments.study_contracts import load_study_manifest

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "study.json"
            path.write_text(json.dumps(self.manifest), encoding="utf-8")
            self.assertEqual(load_study_manifest(path), self.manifest)

    def test_rejects_unknown_or_missing_fields_at_every_level(self):
        cases = [
            ((), "surprise"),
            (("terminal_time_search",), "surprise"),
            (("terminal_time_search", "levels", 0), "surprise"),
            (("solvers", 0), "surprise"),
            (("tolerances", "audit"), "surprise"),
            (("tolerances", "cross_solver"), "surprise"),
            (("tolerances", "convergence"), "surprise"),
        ]
        for path, field in cases:
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                target = manifest
                for key in path:
                    target = target[key]
                target[field] = 1
                with self.assertRaisesRegex(ValueError, "unknown fields"):
                    self.validate(manifest)

        manifest = copy.deepcopy(self.manifest)
        del manifest["legacy_reference"]
        with self.assertRaisesRegex(ValueError, "missing fields"):
            self.validate(manifest)

    def test_requires_exact_model_and_asset_identities(self):
        replacements = {
            "study_id": "free_time_mesh_v2",
            "model_id": "legacy_tf81_v1",
            "legacy_reference": "physical_free_tf_v1",
            "handwritten_asset": "MarsLanding/MarsLandingAuto.c",
        }
        for field, value in replacements.items():
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    self.validate(manifest)

    def test_meshes_are_exact_strictly_increasing_integers_not_booleans(self):
        for meshes in ([20, 40, 30, 60], [20, 30, 30, 60], [20, True, 40, 60]):
            with self.subTest(meshes=meshes):
                manifest = copy.deepcopy(self.manifest)
                manifest["meshes"] = meshes
                with self.assertRaisesRegex(ValueError, "meshes"):
                    self.validate(manifest)

    def test_search_uses_valid_nested_decimal_grids(self):
        invalid = [
            {"lower_s": "80.0"},
            {"upper_s": "75.0"},
            {"levels": [{"step_s": "0"}, {"step_s": "0.05"}]},
            {"levels": [{"step_s": "0.1"}, {"step_s": "0.2"}]},
            {"levels": [{"step_s": "0.3"}, {"step_s": "0.1"}]},
            {"levels": [{"step_s": "0.25"}, {"step_s": "0.1"}]},
            {"levels": [{"step_s": 0.1}, {"step_s": "0.05"}]},
        ]
        for change in invalid:
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.manifest)
                manifest["terminal_time_search"].update(change)
                with self.assertRaisesRegex(ValueError, "decimal grid|terminal_time"):
                    self.validate(manifest)

    def test_v1_freezes_every_search_level_value(self):
        replacements = ["1.00", "0.20", "0.01"]
        for index, replacement in enumerate(replacements):
            with self.subTest(index=index, replacement=replacement):
                manifest = copy.deepcopy(self.manifest)
                manifest["terminal_time_search"]["levels"][index]["step_s"] = replacement
                with self.assertRaisesRegex(ValueError, "pre-registered"):
                    self.validate(manifest)

    def test_solver_roles_are_exact_and_solver_names_are_unique(self):
        bad_solvers = [
            [{"name": "ECOS", "role": "confirmation"}, {"name": "Clarabel", "role": "confirmation"}],
            [{"name": "ECOS", "role": "complete_search"}, {"name": "ECOS", "role": "confirmation"}],
            [{"name": "Clarabel", "role": "complete_search"}, {"name": "ECOS", "role": "confirmation"}],
        ]
        for solvers in bad_solvers:
            with self.subTest(solvers=solvers):
                manifest = copy.deepcopy(self.manifest)
                manifest["solvers"] = solvers
                with self.assertRaisesRegex(ValueError, "solver"):
                    self.validate(manifest)

    def test_all_tolerances_are_positive_finite_numbers_not_booleans(self):
        tolerance_paths = [
            ("audit", "terminal_position_m"),
            ("cross_solver", "fuel_kg"),
            ("convergence", "fuel_change_kg"),
        ]
        for invalid in (0, -1, math.inf, math.nan, True):
            for section, field in tolerance_paths:
                with self.subTest(invalid=invalid, section=section, field=field):
                    manifest = copy.deepcopy(self.manifest)
                    manifest["tolerances"][section][field] = invalid
                    with self.assertRaisesRegex(ValueError, "positive finite"):
                        self.validate(manifest)

    def test_v1_freezes_every_pre_registered_tolerance(self):
        for section, tolerances in self.manifest["tolerances"].items():
            for field, value in tolerances.items():
                with self.subTest(section=section, field=field):
                    manifest = copy.deepcopy(self.manifest)
                    manifest["tolerances"][section][field] = value + 1
                    with self.assertRaisesRegex(ValueError, "pre-registered"):
                        self.validate(manifest)

    def test_provenance_is_required_and_frozen_to_repository_sources(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["provenance"] = EXPECTED_PROVENANCE
        self.assertEqual(self.validate(manifest)["provenance"], EXPECTED_PROVENANCE)

        for field, value in EXPECTED_PROVENANCE.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(manifest)
                changed["provenance"][field] = value + ".changed"
                with self.assertRaisesRegex(ValueError, "provenance"):
                    self.validate(changed)

    def test_provenance_rejects_unknown_and_missing_fields(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["provenance"] = EXPECTED_PROVENANCE

        unknown = copy.deepcopy(manifest)
        unknown["provenance"]["commit"] = "mutable"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.validate(unknown)

        missing = copy.deepcopy(manifest)
        del missing["provenance"]["design_spec"]
        with self.assertRaisesRegex(ValueError, "missing fields"):
            self.validate(missing)


if __name__ == "__main__":
    unittest.main()
