#!/usr/bin/env python3
"""静态检查手写/自动 SOCP 模型的关键尺寸和物理参数是否一致。"""

import ast
import re
import shlex
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


def _cmake_commands(source):
    """提取 CMake 命令 token；注释仅在引号外生效。"""
    commands = []
    errors = []
    index = 0
    while index < len(source):
        if source[index] == "#":
            bracket = re.match(r"#\[(=*)\[", source[index:])
            if bracket:
                closing = "]" + bracket.group(1) + "]"
                end = source.find(closing, index + len(bracket.group()))
                if end < 0:
                    errors.append("CMake 括号注释未闭合 (bracket comment)")
                    break
                index = end + len(closing)
                continue
            index = source.find("\n", index)
            if index < 0:
                break
            continue
        match = re.match(r"[A-Za-z_]\w*", source[index:])
        if not match:
            index += 1
            continue
        name = match.group().lower()
        cursor = index + len(match.group())
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor >= len(source) or source[cursor] != "(":
            index = cursor
            continue
        cursor += 1
        depth, quote, body = 1, None, []
        while cursor < len(source) and depth:
            char = source[cursor]
            if quote:
                body.append(char)
                if char == "\\" and cursor + 1 < len(source):
                    cursor += 1
                    body.append(source[cursor])
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
                body.append(char)
            elif char == "#":
                bracket = re.match(r"#\[(=*)\[", source[cursor:])
                if bracket:
                    closing = "]" + bracket.group(1) + "]"
                    end = source.find(closing, cursor + len(bracket.group()))
                    if end < 0:
                        errors.append("CMake 括号注释未闭合 (bracket comment)")
                        cursor = len(source)
                        break
                    cursor = end + len(closing) - 1
                    body.append(" ")
                    cursor += 1
                    continue
                newline = source.find("\n", cursor)
                cursor = len(source) if newline < 0 else newline
                body.append("\n")
            elif char == "(":
                depth += 1
                body.append(char)
            elif char == ")":
                depth -= 1
                if depth:
                    body.append(char)
            else:
                body.append(char)
            cursor += 1
        escaped_semicolon = "\x00CMAKE_ESCAPED_SEMICOLON\x00"
        token_source = re.sub(r"\\;", escaped_semicolon, "".join(body))
        lexer = shlex.shlex(token_source, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = []
        for token in lexer:
            tokens.extend(part.replace(escaped_semicolon, r"\;")
                          for part in token.split(";") if part != "")
        commands.append((name, tokens))
        index = cursor
    return commands, errors


def _expanded_sources(tokens, variables, resolving=()):
    expanded = []
    for token in tokens:
        match = re.fullmatch(r"\$\{([A-Za-z_]\w*)\}", token)
        if not match:
            expanded.append(token)
            continue
        variable = match.group(1)
        if variable in variables and variable not in resolving:
            values = _expanded_sources(variables[variable], variables,
                                       resolving + (variable,))
            for value in values:
                expanded.extend(_split_cmake_list(value))
    return expanded


def _split_cmake_list(value):
    marker = "\x00CMAKE_ESCAPED_SEMICOLON\x00"
    protected = value.replace(r"\;", marker)
    return [part.replace(marker, r"\;") for part in protected.split(";") if part]


def _forbidden_generated_sources(tokens, variables):
    return [source for source in _expanded_sources(tokens, variables)
            if re.search(r"(?:Auto|Generated)(?:Data)?\.(?:c|cc|cpp)$",
                         source, re.I)]


def _unique_cmake_target(token, variables):
    """展开单个目标 token；生成器表达式、未知变量和多值均不确定。"""
    if "$<" in token:
        return None
    variable = re.fullmatch(r"\$\{([A-Za-z_]\w*)\}", token)
    if variable:
        if variable.group(1) not in variables:
            return None
        values = _expanded_sources(variables[variable.group(1)], variables)
    else:
        values = _split_cmake_list(token)
    return values[0] if len(values) == 1 else None


def validate_handwritten_asset(cmake, handwritten_source):
    """校验手写矩阵实现与自动生成实现仍保持独立。"""
    failures = []
    commands, parse_failures = _cmake_commands(cmake)
    failures.extend(parse_failures)
    variables = {}
    targets = {}
    target_snapshots = {}
    duplicate_targets = set()
    protected_targets = {"ecos_avx", "ecos_scalar"}
    for command, tokens in commands:
        if command == "set" and tokens:
            variables[tokens[0]] = tokens[1:]
        elif command == "list" and len(tokens) >= 2:
            operation, variable = tokens[0].upper(), tokens[1]
            if operation in {"APPEND", "PREPEND", "INSERT"}:
                values = tokens[2:]
                current = list(variables.get(variable, []))
                if operation == "APPEND":
                    variables[variable] = current + values
                elif operation == "PREPEND":
                    variables[variable] = values + current
                elif values:
                    try:
                        position = int(values[0])
                    except ValueError:
                        failures.append(f"CMake list(INSERT {variable}): 索引无法解释")
                    else:
                        position = max(0, min(position, len(current)))
                        variables[variable] = (current[:position] + values[1:] +
                                               current[position:])
        elif command == "add_executable" and tokens:
            target = tokens[0]
            if target in targets:
                duplicate_targets.add(target)
            else:
                targets[target] = tokens[1:]
                target_snapshots[target] = {
                    name: list(values) for name, values in variables.items()
                }
        elif command == "target_sources" and tokens:
            target = _unique_cmake_target(tokens[0], variables)
            source_tokens = [token for token in tokens[1:]
                             if token.upper() not in {"BEFORE", "PRIVATE", "PUBLIC",
                                                      "INTERFACE"}]
            expanded_sources = _expanded_sources(source_tokens, variables)
            generator_sources = [source for source in expanded_sources if "$<" in source]
            forbidden_sources = _forbidden_generated_sources(source_tokens, variables)
            concerning = generator_sources or forbidden_sources
            if target is None and concerning:
                failures.append(
                    "CMake target_sources: 目标无法唯一解析，涉及受关注源/表达式"
                )
            elif target in protected_targets:
                for source in generator_sources:
                    failures.append(
                        f"CMake {target}: 禁止条件源生成器表达式 {source}"
                    )
            for source in forbidden_sources if target in protected_targets else ():
                failures.append(
                    f"CMake {target}: target_sources 禁止自动/生成源 {source}"
                )
        elif command == "set_property" and tokens:
            upper = [token.upper() for token in tokens]
            if upper[0] == "TARGET" and "SOURCES" in upper:
                boundary = min((upper.index(marker) for marker in ("APPEND", "APPEND_STRING",
                               "PROPERTY") if marker in upper), default=len(tokens))
                resolved = [_unique_cmake_target(token, variables)
                            for token in tokens[1:boundary]]
                if any(target in protected_targets for target in resolved):
                    failures.append("CMake SOURCES: 不支持通过 set_property 修改受保护目标")
                elif any(target is None for target in resolved):
                    failures.append("CMake SOURCES: set_property 目标无法唯一解析，不支持")
        elif command == "set_target_properties" and tokens:
            upper = [token.upper() for token in tokens]
            properties = upper.index("PROPERTIES") if "PROPERTIES" in upper else len(tokens)
            if "SOURCES" in upper[properties + 1:]:
                resolved = [_unique_cmake_target(token, variables)
                            for token in tokens[:properties]]
                if any(target in protected_targets for target in resolved):
                    failures.append(
                        "CMake SOURCES: 不支持通过 set_target_properties 修改受保护目标"
                    )
                elif any(target is None for target in resolved):
                    failures.append(
                        "CMake SOURCES: set_target_properties 目标无法唯一解析，不支持"
                    )
    for target in sorted(duplicate_targets):
        failures.append(f"CMake {target}: 重复 add_executable 定义")
    user_sources = variables.get("USER_SOURCES")
    if user_sources is None:
        failures.append("CMake USER_SOURCES: 缺少定义")
    else:
        for filename in ("MarsLanding/MarsLanding.c", "MarsLanding/CRM2CCM.c"):
            if filename not in _expanded_sources(user_sources, variables):
                failures.append(f"CMake USER_SOURCES: 缺少 {filename}")

        forbidden = _forbidden_generated_sources(user_sources, variables)
        failures.extend(f"CMake USER_SOURCES: 禁止自动/生成源 {source}"
                        for source in forbidden)

    all_sources = variables.get("ALL_SOURCES")
    if all_sources is None or "${USER_SOURCES}" not in all_sources:
        failures.append("CMake ALL_SOURCES: 必须包含 ${USER_SOURCES}")

    for target in ("ecos_avx", "ecos_scalar"):
        arguments = targets.get(target)
        if arguments is None or "${ALL_SOURCES}" not in arguments:
            failures.append(f"CMake {target}: 必须从 ${{ALL_SOURCES}} 构建")
            continue
        snapshot = target_snapshots[target]
        forbidden = _forbidden_generated_sources(arguments, snapshot)
        failures.extend(f"CMake {target}: 手写目标闭包禁止自动/生成源 {source}"
                        for source in forbidden)

    auto_arguments = targets.get("ecos_auto")
    if auto_arguments is None or "MarsLanding/MarsLandingAuto.c" not in _expanded_sources(
            auto_arguments, target_snapshots.get("ecos_auto", {})):
        failures.append("CMake ecos_auto: 必须明确使用 MarsLanding/MarsLandingAuto.c")

    forbidden_headers = re.findall(
        r'^\s*#\s*include\s*[<"]([^>"]*(?:AutoData|Generated)[^>"]*)[>"]',
        handwritten_source, re.M | re.I,
    )
    for header in forbidden_headers:
        failures.append(f"MarsLanding.c: 手写源禁止包含生成矩阵数据 {header}")
    return failures


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
        cmake = (ROOT.parent / "CMakeLists.txt").read_text(encoding="utf-8")
    except OSError as error:
        cmake = ""
        failures.append(f"CMakeLists.txt: 无法读取 ({error})")
    try:
        params = python_assignments(inputs["mars_params.py"])
    except SyntaxError as error:
        params = {}
        failures.append(f"mars_params.py: 无法解析 ({error.msg})")
    failures.extend(validate(inputs["MarsLanding.h"], inputs["MarsLanding.c"],
                             inputs["MarsLandingAutoData.h"], params))
    failures.extend(validate_handwritten_asset(cmake, inputs["MarsLanding.c"]))
    if failures:
        for failure in failures:
            print(f"模型一致性检查失败：{failure}")
        return 1

    print("模型一致性检查通过：尺寸、物理参数和手写矩阵资产边界均符合约定。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
