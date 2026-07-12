#!/usr/bin/env python3
"""静态检查手写/自动 SOCP 模型的关键尺寸和物理参数是否一致。"""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def python_assignments(source):
    values = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
            values[target.id] = node.value.value
    return values


def c_macros(source, required_names, label):
    macros = {}
    for name, value in re.findall(r"^[ \t]*#define[ \t]+(\w+)[ \t]+(.+)$", source, re.M):
        macros[name] = re.sub(r"/\*.*?\*/", "", value).strip()

    def value(name, resolving=()):
        if name not in macros:
            raise ValueError(f"缺少宏定义 {name}")
        if name in resolving:
            raise ValueError(f"循环宏定义 {' -> '.join(resolving + (name,))}")
        expression = macros[name]
        expression = re.sub(
            r"\b[A-Za-z_]\w*\b",
            lambda match: str(value(match.group(), resolving + (name,)))
            if match.group() in macros else match.group(),
            expression,
        )
        tree = ast.parse(expression, mode="eval")
        if not all(isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp,
                                      ast.Add, ast.Sub, ast.Mult, ast.Div,
                                      ast.USub, ast.Constant))
                   for node in ast.walk(tree)):
            raise ValueError(f"不支持的宏表达式 {name}")
        return eval(compile(tree, "<macro>", "eval"), {"__builtins__": {}})

    values = {}
    failures = []
    for name in required_names:
        try:
            values[name] = value(name)
        except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as error:
            values[name] = None
            failures.append(f"{label} {name}: 无法解析 ({error})")
    return values, failures


def c_assignment(source, name):
    match = re.search(rf"\b{name}\s*=\s*([^;]+);", source)
    return re.sub(r"\s+", "", match.group(1)) if match else None


def check_equal(failures, actual, expected, label):
    if actual != expected:
        failures.append(f"{label}: 期望 {expected!r}, 实际 {actual!r}")


def check_number(failures, actual, expected, label, converter=float):
    try:
        value = converter(actual)
    except (TypeError, ValueError):
        failures.append(f"{label}: 期望数值 {expected!r}, 实际 {actual!r}")
        return
    check_equal(failures, value, expected, label)


def validate(header, source, auto_header, params):
    """返回全部模型元数据和参数不一致项，而不是在首项失败时中止。"""
    failures = []

    dimensions = {"P_EQ": 223, "M_G": 341, "NNZA": 733, "NNZG": 403}
    header_macros, macro_failures = c_macros(header, dimensions, "MarsLanding.h")
    failures.extend(macro_failures)
    for name, expected in dimensions.items():
        if header_macros[name] is not None:
            check_equal(failures, header_macros[name], expected, f"MarsLanding.h {name}")

    auto_dimensions = {f"{name}_AUTO": value for name, value in dimensions.items()}
    auto_macros, macro_failures = c_macros(auto_header, auto_dimensions,
                                           "MarsLandingAutoData.h")
    failures.extend(macro_failures)
    for name, expected in auto_dimensions.items():
        if auto_macros[name] is not None:
            check_equal(failures, auto_macros[name], expected,
                        f"MarsLandingAutoData.h {name}")

    required_params = ("g_mars", "m0", "T_max", "T_frac", "T2_frac",
                       "n_T", "phi_deg", "theta_deg", "t_f")
    missing_params = [name for name in required_params if name not in params]
    failures.extend(f"mars_params.py {name}: 缺少或不支持的字面量赋值"
                    for name in missing_params)
    if missing_params:
        return failures

    check_equal(failures, c_assignment(source, "g"), str(params["g_mars"]), "g")
    check_number(failures, c_assignment(source, "m_0"), params["m0"], "m_0")
    check_number(failures, c_assignment(source, "T_max"), params["T_max"], "T_max")
    check_equal(failures, c_assignment(source, "T_min"), f"{params['T_frac']}*T_max", "T_min")
    check_equal(failures, c_assignment(source, "T_2"), f"{params['T2_frac']}*T_max", "T_2")
    check_number(failures, c_assignment(source, "n_T"), params["n_T"], "n_T", int)
    check_equal(failures, c_assignment(source, "phi"), f"{params['phi_deg']}*D2R", "phi")
    check_equal(failures, c_assignment(source, "theta_alt"), "(90.0-4.0)*D2R", "theta_alt")
    check_equal(failures, 90.0 - 4.0, params["theta_deg"], "theta_alt 对应角度")
    check_number(failures, c_assignment(source, "t_f"), params["t_f"], "t_f")
    return failures


def main():
    failures = []
    inputs = {}
    for filename in ("MarsLanding.h", "MarsLanding.c", "MarsLandingAutoData.h", "mars_params.py"):
        try:
            inputs[filename] = read(filename)
        except OSError as error:
            inputs[filename] = ""
            failures.append(f"{filename}: 无法读取 ({error})")
    try:
        params = python_assignments(inputs["mars_params.py"])
    except SyntaxError as error:
        params = {}
        failures.append(f"mars_params.py: 无法解析 ({error.msg})")
    failures.extend(validate(inputs["MarsLanding.h"], inputs["MarsLanding.c"],
                             inputs["MarsLandingAutoData.h"], params))
    if failures:
        for failure in failures:
            print(f"模型一致性检查失败：{failure}")
        return 1

    print("模型一致性检查通过：尺寸和物理参数均与 mars_params.py 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
