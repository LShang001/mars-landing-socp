#!/usr/bin/env python3
"""
=============================================================================
 mars_solve.py — 火星着陆轨迹优化 多求解器交叉验证
=============================================================================

 物理约定: x轴向上, 重力向下(-g). 与 C 手写版完全一致.

 方法:
   1. CVXPY + ECOS     (SOCP) — 嵌入式基准
   2. CVXPY + Clarabel (SOCP) — 更快, 更稳定 (Rust 实现)
   3. CasADi + IPOPT   (NLP)  — 独立 NLP 交叉验证
   4. acados + SQP     (NLP)  — 惩罚法, 未来 RTI

 参数来源: mars_params.py (唯一来源)

 用法:  python3 mars_solve.py
 依赖:  pip install casadi cvxpy ecos clarabel numpy
=============================================================================
"""

import numpy as np
import cvxpy as cp
import casadi as ca
from mars_params import *

# ========================== CVXPY (共享建模) ================================

def _build_cvxpy():
    """构造 CVXPY SOCP 问题 (ECOS 和 Clarabel 共用)"""
    r = [cp.Variable(3) for _ in range(N+1)]
    v = [cp.Variable(3) for _ in range(N+1)]
    z = [cp.Variable(1) for _ in range(N+1)]
    u = [cp.Variable(3) for _ in range(N+1)]
    s = [cp.Variable(1) for _ in range(N+1)]

    cst = [r[0] == r0, v[0] == v0, z[0] == np.log(m0), r[N] == 0, v[N] == 0]

    for k in range(N):
        cst += [r[k+1] == r[k] + v[k]*dt + 0.5*u[k]*dt*dt - 0.5*gv*dt*dt]
        cst += [v[k+1] == v[k] + u[k]*dt - gv*dt]
        cst += [z[k+1] == z[k] - alpha*s[k]*dt]

    for k in range(N+1):
        zk, sk = z[k][0], s[k][0]
        cst += [mu1(k)*(zk - z_ref(k) - 1) + sk >= 0]
        cst += [mu2(k)*(zk - z_ref(k) - 1) + sk <= 0]
        cst += [zk >= np.log(m0 - alpha*rho2*k*dt)]
        cst += [zk <= np.log(m0 - alpha*rho1*k*dt)]
        cst += [cp.SOC(r[k][0]*np.tan(theta), cp.vstack([r[k][1], r[k][2]]))]
        cst += [cp.SOC(sk, u[k])]

    prob = cp.Problem(cp.Minimize(sum(s[k] for k in range(N+1))), cst)
    return prob, z


def solve_cvxpy(solver) -> tuple:
    """CVXPY 通用求解 (ECOS 或 Clarabel)"""
    prob, z = _build_cvxpy()
    solver_name = str(solver).split('.')[-1].split("'")[0]
    prob.solve(solver=solver, verbose=False)
    fuel = m0 - np.exp(float(z[N].value[0]))
    return fuel, f"CVXPY+{solver_name}"


# ========================== CasADi + IPOPT ===================================

def solve_ipopt() -> tuple:
    """CasADi NLP + IPOPT (光滑等价 SOC 约束)"""
    NV = 7 + 4  # NX + NU
    nr = NV * (N + 1)
    x = ca.MX.sym('x', nr)

    def _r(k): return x[k*NV:k*NV+3]
    def _v(k): return x[k*NV+3:k*NV+6]
    def _z(k): return x[k*NV+6]
    def _u(k): return x[k*NV+7:k*NV+10]
    def _s(k): return x[k*NV+10]

    g_neg = ca.DM([-0.5*g_mars*dt*dt, 0., 0.])
    g_vel = ca.DM([-g_mars*dt, 0., 0.])

    eq = [ca.vec(_r(0)-r0), ca.vec(_v(0)-v0), _z(0)-np.log(m0),
          ca.vec(_r(N)), ca.vec(_v(N))]
    for k in range(N):
        eq += [ca.vec(_r(k+1)-_r(k)-_v(k)*dt-0.5*_u(k)*dt*dt-g_neg)]
        eq += [ca.vec(_v(k+1)-_v(k)-_u(k)*dt-g_vel)]
        eq += [_z(k+1)-_z(k)+alpha*_s(k)*dt]

    ineq = []
    for k in range(N+1):
        ineq += [mu1(k)*(_z(k)-z_ref(k)-1)+_s(k)]
        ineq += [-mu2(k)*(_z(k)-z_ref(k)-1)-_s(k)]
        ineq += [_z(k)-np.log(m0-alpha*rho2*k*dt)]
        ineq += [-_z(k)+np.log(m0-alpha*rho1*k*dt)]
        ineq += [(_r(k)[0]*np.tan(theta))**2 - _r(k)[1]**2 - _r(k)[2]**2]
        ineq += [_r(k)[0]*np.tan(theta)]
        ineq += [_s(k)**2 - _u(k)[0]**2 - _u(k)[1]**2 - _u(k)[2]**2]
        ineq += [_s(k)]

    eq_flat = ca.vertcat(*eq)
    ineq_flat = ca.vertcat(*ineq)
    g_all = ca.vertcat(eq_flat, ineq_flat)
    nlp = {'x': x, 'f': sum(_s(k) for k in range(N+1)), 'g': g_all}
    S = ca.nlpsol('S', 'ipopt', nlp, {'ipopt.print_level': 0, 'print_time': 0})
    n_eq = eq_flat.size1()
    n_ineq = ineq_flat.size1()
    lbg = ca.DM.zeros(n_eq + n_ineq)
    ubg = ca.vertcat(ca.DM.zeros(n_eq),
                     ca.repmat(ca.DM(float('inf')), n_ineq, 1))
    sol = S(x0=ca.DM.zeros(nr), lbg=lbg, ubg=ubg)
    fuel = m0 - np.exp(float(sol['x'][N*NV+6]))
    return fuel, "CasADi+IPOPT"


# ========================== 主程序 ===========================================

if __name__ == '__main__':
    print("=" * 60)
    print("  火星着陆 SOCP — Python 多求解器交叉验证")
    print("=" * 60)
    print(f"  m0={m0:.0f}kg  N={N}  dt={dt:.1f}s  θ={np.degrees(theta):.1f}°")

    ref = GOLD_STANDARD
    solvers = [
        ("CVXPY+ECOS     (SOCP)", lambda: solve_cvxpy(cp.ECOS)),
        ("CVXPY+Clarabel (SOCP)", lambda: solve_cvxpy(cp.CLARABEL)),
        ("CasADi+IPOPT   (NLP)",  solve_ipopt),
    ]

    try:
        from mars_acados import solve_acados
        solvers.append(("acados SQP     (NLP)", solve_acados))
    except ImportError:
        pass

    for name, fn in solvers:
        try:
            result = fn()
            if result is None:
                print(f"  {name}: 求解失败")
            else:
                fuel, label = result
                dev = (fuel - ref) / ref * 100
                print(f"  {name}: {fuel:.1f} kg ({dev:+.1f}%)")
        except Exception as e:
            print(f"  {name}: ERROR {e}")

    print(f"  C手写版 SOCP:  {ref} kg (基准)")
    print("=" * 60)
