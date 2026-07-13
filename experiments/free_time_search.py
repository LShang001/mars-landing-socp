"""确定性 Decimal 终端时间分层搜索。"""

from decimal import Decimal


def decimal_grid(lower, upper, step):
    lower, upper, step = Decimal(lower), Decimal(upper), Decimal(step)
    if not lower.is_finite() or not upper.is_finite() or not step.is_finite():
        raise ValueError("grid values must be finite")
    if step <= 0 or lower > upper or (upper - lower) % step != 0:
        raise ValueError("grid must be positive, ordered, and endpoint aligned")
    count = int((upper - lower) / step)
    return [lower + step * index for index in range(count + 1)]


def _record(N, tf, level, payload):
    result = {
        "candidate_id": f"N{N}_tf{format(tf, 'f')}",
        "N": N,
        "tf_s": format(tf, "f"),
        "search_level": level,
        "classification": payload["classification"],
        "fuel_kg": payload.get("fuel_kg"),
        "error_type": payload.get("error_type", "none"),
        "error": payload.get("error", ""),
    }
    for name, value in payload.items():
        if name not in result:
            result[name] = value
    return result


def search_mesh(N, lower, upper, levels, solve_candidate):
    """逐层搜索单个网格；异常和失败记录永不丢弃。"""
    lower, upper = Decimal(lower), Decimal(upper)
    records, attempted = [], set()
    for level, step_text in enumerate(levels):
        step = Decimal(step_text)
        if level == 0:
            candidates = decimal_grid(lower, upper, step)
        else:
            successes = [r for r in records if r["classification"] == "success"]
            if not successes:
                break
            best = Decimal(min(successes, key=lambda r: r["fuel_kg"])["tf_s"])
            local_lower, local_upper = max(lower, best - step), min(upper, best + step)
            candidates = decimal_grid(local_lower, local_upper, step)
        for tf in candidates:
            if tf in attempted:
                continue
            attempted.add(tf)
            try:
                payload = solve_candidate(N, tf)
                if not isinstance(payload, dict) or "classification" not in payload:
                    raise ValueError("candidate solver must return a classified mapping")
            except Exception as error:
                payload = {
                    "classification": "solver_error",
                    "fuel_kg": None,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            records.append(_record(N, tf, level, payload))
    return records
