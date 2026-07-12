#!/usr/bin/env python3
"""
=============================================================================
 extract_trajectory.py — 火星着陆轨迹数据提取
=============================================================================
从 CVXPY+ECOS 求解完整轨迹，导出 JSON 供论文图表使用。

输出: paper/data/trajectory.json — 包含完整状态/控制轨迹
      paper/data/solver_comparison.json — 多求解器燃料+性能对比
      paper/data/monte_carlo.json — MC 鲁棒性数据

用法: python3 extract_trajectory.py [--mc N]
=============================================================================
"""
import numpy as np
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'MarsLanding'))
from mars_params import *

# 输出目录
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
#  1. 轨迹提取 (CVXPY+ECOS)
# ============================================================
def extract_trajectory_cvxpy_ecos():
    """用 CVXPY+ECOS 求解并提取完整轨迹"""
    import cvxpy as cp

    # ---- 变量定义 ----
    r = [cp.Variable(3, name=f'r_{k}') for k in range(N+1)]
    v = [cp.Variable(3, name=f'v_{k}') for k in range(N+1)]
    z = [cp.Variable(1, name=f'z_{k}') for k in range(N+1)]
    u = [cp.Variable(3, name=f'u_{k}') for k in range(N+1)]
    s = [cp.Variable(1, name=f's_{k}') for k in range(N+1)]

    constraints = []
    # 边界条件
    constraints += [r[0] == r0, v[0] == v0, z[0] == np.log(m0)]
    constraints += [r[N] == 0, v[N] == 0]

    # 离散动力学
    for k in range(N):
        # rx
        constraints.append(r[k+1][0] == r[k][0] + dt*v[k][0] + 0.5*dt**2*u[k][0] - 0.5*g_mars*dt**2)
        # ry, rz (无重力)
        for j in [1, 2]:
            constraints.append(r[k+1][j] == r[k][j] + dt*v[k][j] + 0.5*dt**2*u[k][j])
        # vx
        constraints.append(v[k+1][0] == v[k][0] + dt*u[k][0] - g_mars*dt)
        # vy, vz
        for j in [1, 2]:
            constraints.append(v[k+1][j] == v[k][j] + dt*u[k][j])
        # z
        constraints.append(z[k+1][0] == z[k][0] - alpha*dt*s[k][0])

    # 不等式约束
    for k in range(N+1):
        z0k = z_ref(k)
        mu1k, mu2k = mu1(k), mu2(k)
        # 质量值不等式 (线性化推力边界)
        constraints.append(s[k] + mu1k*(z[k] - z0k - 1) >= 0)
        constraints.append(s[k] + mu2k*(z[k] - z0k - 1) <= 0)
        # 质量上下界
        constraints.append(z[k] >= np.log(m0 - alpha*rho2*k*dt))
        constraints.append(z[k] <= np.log(m0 - alpha*rho1*k*dt))
        # 下滑角锥
        constraints.append(cp.SOC(r[k][0]*np.tan(theta), cp.vstack([r[k][1], r[k][2]])))
        # 推力松弛锥
        constraints.append(cp.SOC(s[k], cp.vstack([u[k][0], u[k][1], u[k][2]])))

    # 目标
    objective = cp.Minimize(cp.sum([s[k] for k in range(N+1)]))

    # 求解
    prob = cp.Problem(objective, constraints)
    t0 = time.perf_counter()
    prob.solve(solver=cp.ECOS, verbose=False)
    elapsed = time.perf_counter() - t0

    if prob.status not in ('optimal', 'optimal_inaccurate'):
        raise RuntimeError(f'ECOS 求解失败: {prob.status}')

    # 提取轨迹
    traj = {
        'N': N, 'dt': dt, 'tf': t_f,
        'm0': m0, 'g_mars': g_mars,
        'fuel': float(m0 - np.exp(z[N].value[0])),
        'solve_time_ms': elapsed * 1000,
        'status': prob.status,
        'time': [k*dt for k in range(N+1)],
        'rx': [float(r[k].value[0]) for k in range(N+1)],
        'ry': [float(r[k].value[1]) for k in range(N+1)],
        'rz': [float(r[k].value[2]) for k in range(N+1)],
        'vx': [float(v[k].value[0]) for k in range(N+1)],
        'vy': [float(v[k].value[1]) for k in range(N+1)],
        'vz': [float(v[k].value[2]) for k in range(N+1)],
        'mass': [float(np.exp(z[k].value[0])) for k in range(N+1)],
        'z': [float(z[k].value[0]) for k in range(N+1)],
        'ux': [float(u[k].value[0]) for k in range(N+1)],
        'uy': [float(u[k].value[1]) for k in range(N+1)],
        'uz': [float(u[k].value[2]) for k in range(N+1)],
        'sigma': [float(s[k].value[0]) for k in range(N+1)],
        'thrust_norm': [float(np.sqrt(u[k].value[0]**2 + u[k].value[1]**2 + u[k].value[2]**2))
                        for k in range(N+1)],
        'glide_margin': [float(r[k].value[0]*np.tan(theta) -
                         np.sqrt(r[k].value[1]**2 + r[k].value[2]**2))
                         for k in range(N+1)],
    }
    return traj


# ============================================================
#  2. 多求解器对比
# ============================================================
def extract_solver_comparison():
    """运行 mars_solve.py 所有求解器，收集燃料+性能"""
    import cvxpy as cp
    import casadi as ca

    results = []

    # --- CVXPY+ECOS ---
    try:
        r = [cp.Variable(3) for _ in range(N+1)]
        v = [cp.Variable(3) for _ in range(N+1)]
        z = [cp.Variable(1) for _ in range(N+1)]
        u = [cp.Variable(3) for _ in range(N+1)]
        s = [cp.Variable(1) for _ in range(N+1)]

        cstr = []
        cstr += [r[0] == r0, v[0] == v0, z[0] == np.log(m0)]
        cstr += [r[N] == 0, v[N] == 0]
        for k in range(N):
            cstr.append(r[k+1][0] == r[k][0] + dt*v[k][0] + 0.5*dt**2*u[k][0] - 0.5*g_mars*dt**2)
            for j in [1,2]:
                cstr.append(r[k+1][j] == r[k][j] + dt*v[k][j] + 0.5*dt**2*u[k][j])
            cstr.append(v[k+1][0] == v[k][0] + dt*u[k][0] - g_mars*dt)
            for j in [1,2]:
                cstr.append(v[k+1][j] == v[k][j] + dt*u[k][j])
            cstr.append(z[k+1][0] == z[k][0] - alpha*dt*s[k][0])
        for k in range(N+1):
            z0k, m1, m2 = z_ref(k), mu1(k), mu2(k)
            cstr.append(s[k] + m1*(z[k] - z0k - 1) >= 0)
            cstr.append(s[k] + m2*(z[k] - z0k - 1) <= 0)
            cstr.append(z[k] >= np.log(m0 - alpha*rho2*k*dt))
            cstr.append(z[k] <= np.log(m0 - alpha*rho1*k*dt))
            cstr.append(cp.SOC(r[k][0]*np.tan(theta), cp.vstack([r[k][1], r[k][2]])))
            cstr.append(cp.SOC(s[k], cp.vstack([u[k][0], u[k][1], u[k][2]])))

        prob = cp.Problem(cp.Minimize(cp.sum(s)), cstr)
        t0 = time.perf_counter()
        prob.solve(solver=cp.ECOS, verbose=False)
        t1 = time.perf_counter()
        fuel = m0 - np.exp(z[N].value[0])
        results.append({'solver': 'CVXPY+ECOS', 'type': 'SOCP', 'fuel_kg': round(float(fuel), 1),
                        'time_ms': round((t1-t0)*1000, 2), 'status': prob.status})
    except Exception as e:
        results.append({'solver': 'CVXPY+ECOS', 'type': 'SOCP', 'fuel_kg': None, 'time_ms': None, 'status': str(e)})

    # --- CVXPY+Clarabel ---
    try:
        r2 = [cp.Variable(3) for _ in range(N+1)]
        v2 = [cp.Variable(3) for _ in range(N+1)]
        z2 = [cp.Variable(1) for _ in range(N+1)]
        u2 = [cp.Variable(3) for _ in range(N+1)]
        s2 = [cp.Variable(1) for _ in range(N+1)]

        cstr2 = []
        cstr2 += [r2[0] == r0, v2[0] == v0, z2[0] == np.log(m0)]
        cstr2 += [r2[N] == 0, v2[N] == 0]
        for k in range(N):
            cstr2.append(r2[k+1][0] == r2[k][0] + dt*v2[k][0] + 0.5*dt**2*u2[k][0] - 0.5*g_mars*dt**2)
            for j in [1,2]:
                cstr2.append(r2[k+1][j] == r2[k][j] + dt*v2[k][j] + 0.5*dt**2*u2[k][j])
            cstr2.append(v2[k+1][0] == v2[k][0] + dt*u2[k][0] - g_mars*dt)
            for j in [1,2]:
                cstr2.append(v2[k+1][j] == v2[k][j] + dt*u2[k][j])
            cstr2.append(z2[k+1][0] == z2[k][0] - alpha*dt*s2[k][0])
        for k in range(N+1):
            z0k, m1, m2 = z_ref(k), mu1(k), mu2(k)
            cstr2.append(s2[k] + m1*(z2[k] - z0k - 1) >= 0)
            cstr2.append(s2[k] + m2*(z2[k] - z0k - 1) <= 0)
            cstr2.append(z2[k] >= np.log(m0 - alpha*rho2*k*dt))
            cstr2.append(z2[k] <= np.log(m0 - alpha*rho1*k*dt))
            cstr2.append(cp.SOC(r2[k][0]*np.tan(theta), cp.vstack([r2[k][1], r2[k][2]])))
            cstr2.append(cp.SOC(s2[k], cp.vstack([u2[k][0], u2[k][1], u2[k][2]])))

        prob2 = cp.Problem(cp.Minimize(cp.sum(s2)), cstr2)
        t0 = time.perf_counter()
        prob2.solve(solver=cp.CLARABEL, verbose=False)
        t1 = time.perf_counter()
        fuel = m0 - np.exp(z2[N].value[0])
        results.append({'solver': 'CVXPY+Clarabel', 'type': 'SOCP', 'fuel_kg': round(float(fuel), 1),
                        'time_ms': round((t1-t0)*1000, 2), 'status': prob2.status})
    except Exception as e:
        results.append({'solver': 'CVXPY+Clarabel', 'type': 'SOCP', 'fuel_kg': None, 'time_ms': None, 'status': str(e)})

    # --- CasADi+IPOPT ---
    try:
        import casadi as ca
        NV = 7; NU_ctrl = 4; NVAR = NV + NU_ctrl  # 11
        x = ca.MX.sym('x', NVAR*(N+1))
        _r = lambda k: x[k*NVAR:k*NVAR+3]
        _v = lambda k: x[k*NVAR+3:k*NVAR+6]
        _z = lambda k: x[k*NVAR+6]
        _u = lambda k: x[k*NVAR+7:k*NVAR+10]
        _s = lambda k: x[k*NVAR+10]

        eqs = []
        ineqs = []
        eqs += [_r(0)[0]-r0[0], _r(0)[1]-r0[1], _r(0)[2]-r0[2]]
        eqs += [_v(0)[0]-v0[0], _v(0)[1]-v0[1], _v(0)[2]-v0[2]]
        eqs += [_z(0)-np.log(m0)]
        eqs += [_r(N)[0], _r(N)[1], _r(N)[2]]
        eqs += [_v(N)[0], _v(N)[1], _v(N)[2]]

        for k in range(N):
            eqs.append(_r(k+1)[0] - _r(k)[0] - dt*_v(k)[0] - 0.5*dt**2*_u(k)[0] + 0.5*g_mars*dt**2)
            for j in [1,2]:
                eqs.append(_r(k+1)[j] - _r(k)[j] - dt*_v(k)[j] - 0.5*dt**2*_u(k)[j])
            eqs.append(_v(k+1)[0] - _v(k)[0] - dt*_u(k)[0] + g_mars*dt)
            for j in [1,2]:
                eqs.append(_v(k+1)[j] - _v(k)[j] - dt*_u(k)[j])
            eqs.append(_z(k+1) - _z(k) + alpha*dt*_s(k))

        for k in range(N+1):
            z0k, m1, m2 = z_ref(k), mu1(k), mu2(k)
            ineqs.append(_s(k) + m1*(_z(k) - z0k - 1))
            ineqs.append(-_s(k) - m2*(_z(k) - z0k - 1))
            ineqs.append(_z(k) - np.log(m0 - alpha*rho2*k*dt))
            ineqs.append(-_z(k) + np.log(m0 - alpha*rho1*k*dt))
            ineqs.append((_r(k)[0]*np.tan(theta))**2 - _r(k)[1]**2 - _r(k)[2]**2)
            ineqs.append(_s(k)**2 - _u(k)[0]**2 - _u(k)[1]**2 - _u(k)[2]**2)
            ineqs.append(_r(k)[0]*np.tan(theta))
            ineqs.append(_s(k))

        obj = ca.sum1(ca.vertcat(*[_s(k) for k in range(N+1)]))
        nlp = {'x': x, 'f': obj, 'g': ca.vertcat(*eqs + ineqs)}
        opts = {'ipopt.print_level': 0, 'ipopt.sb': 'yes', 'print_time': 0}
        solver = ca.nlpsol('solver', 'ipopt', nlp, opts)

        lbg = [0]*len(eqs) + [0]*len(ineqs)
        ubg = [0]*len(eqs) + [np.inf]*len(ineqs)

        t0 = time.perf_counter()
        sol = solver(x0=np.zeros(NVAR*(N+1)), lbg=lbg, ubg=ubg)
        t1 = time.perf_counter()
        sol_x = np.array(sol['x']).flatten()
        zf = float(sol_x[N*NVAR+6])
        fuel = m0 - np.exp(zf)
        results.append({'solver': 'CasADi+IPOPT', 'type': 'NLP',
                        'fuel_kg': round(float(fuel), 1),
                        'time_ms': round((t1-t0)*1000, 2),
                        'status': 'optimal' if solver.stats()['success'] else 'failed'})
    except Exception as e:
        results.append({'solver': 'CasADi+IPOPT', 'type': 'NLP', 'fuel_kg': None, 'time_ms': None, 'status': str(e)})

    return results


# ============================================================
#  3. 主流程
# ============================================================
if __name__ == '__main__':
    print('=' * 60)
    print('  火星着陆 轨迹数据提取')
    print('=' * 60)

    # 3.1 轨迹提取
    print('\n[1/3] 提取完整轨迹 (CVXPY+ECOS)...')
    traj = extract_trajectory_cvxpy_ecos()
    traj_path = DATA_DIR / 'trajectory.json'
    with open(traj_path, 'w') as f:
        json.dump(traj, f, indent=2, ensure_ascii=False)
    print(f'  燃料: {traj["fuel"]:.1f} kg, 求解耗时: {traj["solve_time_ms"]:.1f} ms')
    print(f'  轨迹数据已保存: {traj_path}')

    # 3.2 多求解器对比
    print('\n[2/3] 多求解器对比...')
    results = extract_solver_comparison()
    cmp_path = DATA_DIR / 'solver_comparison.json'
    with open(cmp_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    for r in results:
        status = f'{r["fuel_kg"]} kg' if r['fuel_kg'] else f'FAIL: {r["status"]}'
        print(f'  {r["solver"]:20s} ({r["type"]:4s}): {status} ({r["time_ms"]} ms)' if r["time_ms"] else f'  {r["solver"]:20s} ({r["type"]:4s}): {status}')
    print(f'  对比数据已保存: {cmp_path}')

    print('\n[3/3] 完成！运行 paper/figures/generate_all.py 生成图表。')
