#!/bin/bash
# ===========================================================================
# ci/validate.sh — 火星着陆项目全求解器验证
# 运行: bash ci/validate.sh
# ===========================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

PASS=0; FAIL=0
check() {
    local label="$1" val="$2"
    if [ "$val" = "FAIL" ]; then
        echo -e "  ${RED}❌${NC} $label: FAIL"; FAIL=$((FAIL+1)); return
    fi
    if [[ ! "$val" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        echo -e "  ${RED}❌${NC} $label: FAIL (invalid numeric result: $val)"; FAIL=$((FAIL+1)); return
    fi
    if python3 -c "exit(0 if abs(float('$val')-400.7)<0.5 else 1)"; then
        echo -e "  ${GREEN}✅${NC} $label: $val kg"; PASS=$((PASS+1))
    else
        echo -e "  ${RED}❌${NC} $label: $val kg (expected 400.7)"; FAIL=$((FAIL+1))
    fi
}
extract_fuel() {
    awk '/^[[:space:]]*燃料消耗[[:space:]]*:[[:space:]]*[0-9]+([.][0-9]+)?[[:space:]]+kg$/ ||
         /^[[:space:]]*燃料[[:space:]]*:[[:space:]]*[0-9]+([.][0-9]+)?[[:space:]]+kg  [(]✅[)]$/ {
        value = $0
        sub(/^[^:]*:[[:space:]]*/, "", value)
        sub(/[[:space:]]+kg.*/, "", value)
        print value
        exit
    }'
}
run_solver() {
    local label="$1" output value
    shift
    if ! output=$("$@" 2>&1); then
        echo "  $label command failed:" >&2
        printf '%s\n' "$output" >&2
        printf 'FAIL\n'
        return 0
    fi
    value=$(printf '%s\n' "$output" | extract_fuel)
    if [ -z "$value" ]; then
        echo "  $label did not emit a fuel value:" >&2
        printf '%s\n' "$output" >&2
        printf 'FAIL\n'
        return 0
    fi
    printf '%s\n' "$value"
}
run_py() {
    local label="$1" code="$2" output value
    if ! output=$(python3 -c "$code" 2>&1); then
        echo "  $label command failed:" >&2
        printf '%s\n' "$output" >&2
        printf 'FAIL\n'
        return 0
    fi
    value=$(printf '%s\n' "$output" | awk '/^[0-9]+([.][0-9]+)?$/ { result = $0 } END { print result }')
    if [ -z "$value" ]; then
        echo "  $label did not emit one numeric result:" >&2
        printf '%s\n' "$output" >&2
        printf 'FAIL\n'
        return 0
    fi
    printf '%s\n' "$value"
}

echo "============================================================"
echo "  火星着陆 SOCP — 全求解器验证"
echo "============================================================"

# --- 静态模型一致性 ---
python3 MarsLanding/check_model_consistency.py

# --- C 嵌入式 ---
echo ""; echo "--- C 嵌入式 ---"
for t in ecos_avx ecos_scalar ecos_auto; do
    r=$(run_solver "C ${t#ecos_}" "./build/bin/$t")
    check "C ${t#ecos_}" "$r"
done

# --- Clarabel C ---
if [ -f build/bin/ecos_clarabel ]; then
    r=$(run_solver "C Clarabel" env LD_LIBRARY_PATH=/usr/local/lib ./build/bin/ecos_clarabel)
    check "C Clarabel  " "$r"
fi

# --- Python ---
echo ""; echo "--- Python 求解器 ---"
export ACADOS_SOURCE_DIR="${ACADOS_SOURCE_DIR:-/opt/acados}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}/opt/acados/lib"
cd MarsLanding

r=$(run_py "CVXPY+ECOS" "from mars_params import *; from mars_solve import solve_cvxpy; import cvxpy as cp; f,_=solve_cvxpy(cp.ECOS); print(f'{f:.1f}')")
check "CVXPY+ECOS   " "$r"

r=$(run_py "CVXPY+Clarabel" "from mars_params import *; from mars_solve import solve_cvxpy; import cvxpy as cp; f,_=solve_cvxpy(cp.CLARABEL); print(f'{f:.1f}')")
check "CVXPY+Clarabel" "$r"

r=$(run_py "CasADi+IPOPT" "from mars_solve import solve_ipopt; f,_=solve_ipopt(); print(f'{f:.1f}')")
check "CasADi+IPOPT  " "$r"

if [ "${1:-}" = "--full" ]; then
    echo ""; echo "--- 扩展测试 ---"
    r=$(run_py "acados SQP" "from mars_acados import solve_acados; r=solve_acados(); print(f'{r[0]:.1f}' if r else 'FAIL')")
    check "acados SQP    " "$r"
    r=$(run_py "Monte Carlo" "from mars_robustness import monte_carlo; rate,_=monte_carlo(20); print(f'{rate:.0f}')")
    if [[ "$r" =~ ^[0-9]+$ ]] && [ "$r" -gt 40 ]; then
        echo -e "  ${GREEN}✅${NC} Monte Carlo : ${r}% success"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}❌${NC} Monte Carlo : ${r}% (< 40%)"
        FAIL=$((FAIL+1))
    fi
fi

# --- Summary ---
echo ""; echo "============================================================"
echo -e "  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
echo "============================================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
