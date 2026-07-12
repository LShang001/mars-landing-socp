import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_model_consistency", ROOT / "MarsLanding" / "check_model_consistency.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


VALID_CMAKE = """
set(USER_SOURCES
    "MarsLanding/MarsLanding.c"
    "MarsLanding/CRM2CCM.c"
)
set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})
add_executable(ecos_avx ${ALL_SOURCES})
add_executable(ecos_scalar ${ALL_SOURCES})
add_executable(ecos_auto ${ECOS_CORE_SOURCES} MarsLanding/MarsLandingAuto.c)
"""


class HandwrittenAssetTest(unittest.TestCase):
    def test_current_build_keeps_independent_targets(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        handwritten_source = (ROOT / "MarsLanding" / "MarsLanding.c").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            CHECKER.validate_handwritten_asset(cmake, handwritten_source), []
        )

    def test_accepts_independent_handwritten_build(self):
        self.assertEqual(CHECKER.validate_handwritten_asset(VALID_CMAKE, "int main(void) {}"), [])

    def test_requires_both_handwritten_user_sources(self):
        cmake = VALID_CMAKE.replace('    "MarsLanding/CRM2CCM.c"\n', "")
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("CRM2CCM.c" in failure for failure in failures))

    def test_requires_handwritten_targets_to_use_all_sources(self):
        cmake = VALID_CMAKE.replace("add_executable(ecos_scalar ${ALL_SOURCES})",
                                    "add_executable(ecos_scalar ${USER_SOURCES})")
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("ecos_scalar" in failure and "ALL_SOURCES" in failure
                            for failure in failures))

    def test_requires_auto_target_to_use_auto_source(self):
        cmake = VALID_CMAKE.replace("MarsLanding/MarsLandingAuto.c", "MarsLanding/MarsLanding.c")
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("ecos_auto" in failure and "MarsLandingAuto.c" in failure
                            for failure in failures))

    def test_rejects_generated_matrix_data_in_handwritten_source(self):
        source = '#include "MarsLandingAutoData.h"\nint main(void) {}'
        failures = CHECKER.validate_handwritten_asset(VALID_CMAKE, source)
        self.assertTrue(any("MarsLandingAutoData.h" in failure for failure in failures))

    def test_rejects_auto_source_in_handwritten_target_variable_closure(self):
        cmake = VALID_CMAKE.replace(
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES} MarsLanding/MarsLandingAuto.c)",
        )
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("ecos_avx" in failure and "MarsLandingAuto.c" in failure
                            for failure in failures))

    def test_rejects_auto_source_in_user_sources(self):
        cmake = VALID_CMAKE.replace(
            '    "MarsLanding/CRM2CCM.c"',
            '    "MarsLanding/CRM2CCM.c"\n    MarsLanding/MarsLandingAuto.c',
        )
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("USER_SOURCES" in failure and "MarsLandingAuto.c" in failure
                            for failure in failures))

    def test_ignores_required_source_written_only_in_comment(self):
        cmake = VALID_CMAKE.replace(
            '    "MarsLanding/CRM2CCM.c"',
            '    # "MarsLanding/CRM2CCM.c"',
        )
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("CRM2CCM.c" in failure for failure in failures))

    def test_ignores_variable_reference_written_only_in_comment(self):
        cmake = VALID_CMAKE.replace(
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} # ${USER_SOURCES}\n)",
        )
        failures = CHECKER.validate_handwritten_asset(cmake, "int main(void) {}")
        self.assertTrue(any("ALL_SOURCES" in failure and "USER_SOURCES" in failure
                            for failure in failures))

    def test_hash_inside_quoted_token_is_not_a_comment(self):
        cmake = VALID_CMAKE.replace(
            '    "MarsLanding/MarsLanding.c"',
            '    "label#kept"\n    "MarsLanding/MarsLanding.c"',
        )
        self.assertEqual(CHECKER.validate_handwritten_asset(cmake, "int main(void) {}"), [])

    def test_ignores_multiline_bracket_comments_with_equals(self):
        cmake = VALID_CMAKE.replace(
            "set(USER_SOURCES",
            "#[=[ fake set(USER_SOURCES MarsLanding/MarsLandingAuto.c)\n]=]\nset(USER_SOURCES",
        )
        self.assertEqual(CHECKER.validate_handwritten_asset(cmake, "int main(void) {}"), [])

    def test_unclosed_bracket_comment_fails_closed(self):
        failures = CHECKER.validate_handwritten_asset(
            VALID_CMAKE + "\n#[[ never closed", "int main(void) {}"
        )
        self.assertTrue(any("bracket" in failure.lower() or "括号注释" in failure
                            for failure in failures))

    def test_rejects_auto_source_at_each_list_position(self):
        for value in (
            "MarsLanding/MarsLandingAuto.c;safe.c;other.c",
            "safe.c;MarsLanding/MarsLandingAuto.c;other.c",
            "safe.c;other.c;MarsLanding/MarsLandingAuto.c",
        ):
            with self.subTest(value=value):
                cmake = VALID_CMAKE.replace(
                    "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
                    f"set(ALL_SOURCES ${{ECOS_CORE_SOURCES}} ${{USER_SOURCES}} {value})",
                )
                self.assertTrue(any("MarsLandingAuto.c" in failure for failure in
                                    CHECKER.validate_handwritten_asset(cmake, "")))

    def test_splits_lists_created_by_variable_expansion(self):
        cmake = VALID_CMAKE.replace(
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
            "set(EXTRA safe.c;MarsLanding/MarsLandingAuto.c)\n"
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES} ${EXTRA})",
        )
        self.assertTrue(any("MarsLandingAuto.c" in failure for failure in
                            CHECKER.validate_handwritten_asset(cmake, "")))

    def test_escaped_semicolon_does_not_split_a_list_item(self):
        cmake = VALID_CMAKE.replace(
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
            r"set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES} safe\;name.c)",
        )
        self.assertEqual(CHECKER.validate_handwritten_asset(cmake, ""), [])

    def test_target_uses_variable_snapshot_before_safe_reset(self):
        cmake = VALID_CMAKE.replace(
            "add_executable(ecos_avx ${ALL_SOURCES})",
            "set(ALL_SOURCES ${USER_SOURCES} MarsLanding/MarsLandingAuto.c)\n"
            "add_executable(ecos_avx ${ALL_SOURCES})\n"
            "set(ALL_SOURCES ${ECOS_CORE_SOURCES} ${USER_SOURCES})",
        )
        self.assertTrue(any("ecos_avx" in failure and "MarsLandingAuto.c" in failure
                            for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_duplicate_target_fails_explicitly(self):
        cmake = VALID_CMAKE.replace(
            "add_executable(ecos_avx ${ALL_SOURCES})",
            "add_executable(ecos_avx ${ALL_SOURCES})\n"
            "add_executable(ecos_avx ${ALL_SOURCES})",
        )
        self.assertTrue(any("ecos_avx" in failure and "重复" in failure
                            for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_list_mutations_cannot_inject_auto_source(self):
        mutations = (
            "list(APPEND ALL_SOURCES MarsLanding/MarsLandingAuto.c)",
            "list(PREPEND ALL_SOURCES MarsLanding/MarsLandingAuto.c)",
            "list(INSERT ALL_SOURCES 1 MarsLanding/MarsLandingAuto.c)",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                cmake = VALID_CMAKE.replace(
                    "add_executable(ecos_avx ${ALL_SOURCES})",
                    mutation + "\nadd_executable(ecos_avx ${ALL_SOURCES})",
                )
                self.assertTrue(any("ecos_avx" in failure and "MarsLandingAuto.c" in failure
                                    for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_target_sources_rejects_auto_source_through_variable_list(self):
        cmake = VALID_CMAKE.replace(
            "add_executable(ecos_avx ${ALL_SOURCES})",
            "set(EXTRA safe.c;MarsLanding/MarsLandingAuto.c)\n"
            "add_executable(ecos_avx ${ALL_SOURCES})\n"
            "target_sources(ecos_avx BEFORE PRIVATE ${EXTRA})",
        )
        self.assertTrue(any("ecos_avx" in failure and "MarsLandingAuto.c" in failure
                            for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_source_property_mutations_fail_closed(self):
        mutations = (
            "set_property(TARGET ecos_avx APPEND PROPERTY SOURCES safe.c)",
            "set_target_properties(ecos_scalar PROPERTIES SOURCES safe.c)",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                failures = CHECKER.validate_handwritten_asset(VALID_CMAKE + mutation, "")
                self.assertTrue(any("SOURCES" in failure and "不支持" in failure
                                    for failure in failures))

    def test_target_sources_expands_target_variable(self):
        cmake = VALID_CMAKE + (
            "\nset(T ecos_avx)\n"
            "target_sources(${T} PRIVATE MarsLanding/MarsLandingAuto.c)"
        )
        self.assertTrue(any("ecos_avx" in failure and "MarsLandingAuto.c" in failure
                            for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_target_sources_rejects_generator_expression_source(self):
        cmake = VALID_CMAKE + (
            "\ntarget_sources(ecos_scalar PRIVATE "
            "$<$<BOOL:1>:MarsLanding/MarsLandingAuto.c>)"
        )
        self.assertTrue(any("ecos_scalar" in failure and "生成器表达式" in failure
                            for failure in CHECKER.validate_handwritten_asset(cmake, "")))

    def test_property_commands_expand_target_variables(self):
        mutations = (
            "set(T ecos_avx)\nset_property(TARGET ${T} PROPERTY SOURCES safe.c)",
            "set(T ecos_scalar)\nset_target_properties(${T} PROPERTIES SOURCES safe.c)",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                failures = CHECKER.validate_handwritten_asset(VALID_CMAKE + mutation, "")
                self.assertTrue(any("SOURCES" in failure and "不支持" in failure
                                    for failure in failures))


if __name__ == "__main__":
    unittest.main()
