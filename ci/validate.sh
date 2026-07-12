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
    if [ -z "$val" ] || [ "$val" = "FAIL" ]; then
        echo -e "  ${RED}❌${NC} $label: FAIL"; FAIL=$((FAIL+1)); return
    fi
    val=$(echo "$val" | tr -cd '0-9.')
    if python3 -c "exit(0 if abs(float('$val')-400.7)<0.5 else 1)"; then
        echo -e "  ${GREEN}✅${NC} $label: $val kg"; PASS=$((PASS+1))
    else
        echo -e "  ${RED}❌${NC} $label: $val kg (expected 400.7)"; FAIL=$((FAIL+1))
    fi
}
run_py() { python3 -c "import sys,os; sys.stderr=os.fdopen(os.open('/dev/null',os.O_WRONLY)); $1" 2>/dev/null | tail -1; }

echo "============================================================"
echo "  火星着陆 SOCP — 全求解器验证"
echo "============================================================"

# --- C 嵌入式 ---
echo ""; echo "--- C 嵌入式 ---"
for t in ecos_avx ecos_scalar ecos_auto; do
    r=$(./build/bin/$t 2>/dev/null | grep "燃料" | awk '{print $(NF-1)}')
    check "C ${t#ecos_}" "$r"
done

# --- Clarabel C ---
if [ -f build/bin/ecos_clarabel ]; then
    r=$(LD_LIBRARY_PATH=/usr/local/lib ./build/bin/ecos_clarabel 2>/dev/null | grep "燃料:" | grep -oP '[\d.]+')
    check "C Clarabel  " "$r"
fi

# --- Python ---
echo ""; echo "--- Python 求解器 ---"
export ACADOS_SOURCE_DIR="${ACADOS_SOURCE_DIR:-/opt/acados}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}/opt/acados/lib"
cd MarsLanding

r=$(run_py "from mars_params import *; from mars_solve import solve_cvxpy; import cvxpy as cp; f,_=solve_cvxpy(cp.ECOS); print(f'{f:.1f}')")
check "CVXPY+ECOS   " "$r"

r=$(run_py "from mars_params import *; from mars_solve import solve_cvxpy; import cvxpy as cp; f,_=solve_cvxpy(cp.CLARABEL); print(f'{f:.1f}')")
check "CVXPY+Clarabel" "$r"

r=$(run_py "from mars_solve import solve_ipopt; f,_=solve_ipopt(); print(f'{f:.1f}')" | grep -oP '[\d.]+')
check "CasADi+IPOPT  " "$r"

if [ "${1:-}" = "--full" ]; then
    echo ""; echo "--- 扩展测试 ---"
    r=$(run_py "from mars_acados import solve_acados; r=solve_acados(); print('RESULT='+f'{r[0]:.1f}' if r else 'RESULT=FAIL')" | grep 'RESULT=' | cut -d= -f2)
    check "acados SQP    " "$r"
    r=$(run_py "from mars_robustness import monte_carlo; rate,_=monte_carlo(20); print(f'RATE={rate:.0f}')" | grep 'RATE=' | cut -d= -f2)
    if [ -n "$r" ] && [ "$r" -gt 40 ]; then
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
