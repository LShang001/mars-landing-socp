#!/usr/bin/env python3
"""
=============================================================================
 mars_acados.py — 火星着陆轨迹优化 acados SQP 求解器 (实验性)
=============================================================================

 使用 acados (SQP + HPIPM) 直接求解 NLP, 不经过 SOC 凸化。
 与 ECOS (SOCP) 和 IPOPT (NLP) 并列, 作为第三求解器进行交叉验证。

 当前状态 (2026-07-13):
   ✅ 安装成功: acados v0.5.1 + HPIPM + BLASFEO
   ✅ 离散动力学 + 终端约束正确
   ✅ SQP 收敛
   ⚠️  非线性路径约束 (推力锥/下滑角) 需进一步调参
   ⚠️  当前 NLP 解 ~256 kg, 与 ECOS SOCP 400.7 kg 有偏差
       原因: con_h_expr 在初始阶段的强制方式需调整

 用法:  python3 mars_acados.py

 依赖:  export ACADOS_SOURCE_DIR=/opt/acados
        export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/acados/lib

 作者: LShang + Claude
 日期: 2026-07-13
=============================================================================
"""

import numpy as np
import casadi as ca

# ========================== 物理参数 =========================================

N  = 30; NX = 7; NU = 4
g  = 3.7114; g_e = 9.807; m0 = 1905.0
Isp = 225.0; T_max_co = 3.1e3
T_min_co = 0.3 * T_max_co; T2 = 0.8 * T_max_co; nT = 6
t_f = 81.0; dt = t_f / N
phi   = 27.0 * np.pi / 180.0
theta = (90.0 - 4.0) * np.pi / 180.0
alpha = 1.0 / (Isp * g_e * np.cos(phi))
rho1  = nT * T_min_co * np.cos(phi)   # 最小有效推力 [N]
rho2  = nT * T2       * np.cos(phi)   # 最大有效推力 [N] (80% 额定)
tan_theta = np.tan(theta)


# ========================== acados OCP 建模 ===================================

from acados_template import AcadosOcp, AcadosModel

def create_ocp():
    """ 构造 acados OCP 问题。

    注意:
    - 使用 NONLINEAR_LS 代价 (GAUSS_NEWTON Hessian 需要)
    - 非线性约束用 sqrt 形式 (比平方形式线性化更好)
    - 推力上下界暂未加入 (exp(-z) 导致 QP 不稳定)
    """
    ocp = AcadosOcp()
    ocp.model.name = 'mars_landing'
    ocp.solver_options.N_horizon = N
    ocp.solver_options.tf = t_f

    # ---- 符号变量 ----
    x_sym = ca.MX.sym('x', NX)   # [rx, ry, rz, vx, vy, vz, z=ln(m)]
    u_sym = ca.MX.sym('u', NU)   # [ux, uy, uz, sigma]

    rx, ry, rz = x_sym[0], x_sym[1], x_sym[2]
    vx, vy, vz = x_sym[3], x_sym[4], x_sym[5]
    z_state    = x_sym[6]
    ux, uy, uz = u_sym[0], u_sym[1], u_sym[2]
    sigma      = u_sym[3]

    # ---- 离散动力学 ----
    rx_next = rx + vx*dt + 0.5*ux*dt*dt - 0.5*g*dt*dt
    ry_next = ry + vy*dt + 0.5*uy*dt*dt
    rz_next = rz + vz*dt + 0.5*uz*dt*dt
    vx_next = vx + ux*dt - g*dt
    vy_next = vy + uy*dt
    vz_next = vz + uz*dt
    z_next  = z_state - alpha*sigma*dt

    x_next = ca.vertcat(rx_next, ry_next, rz_next,
                         vx_next, vy_next, vz_next, z_next)

    # ---- 模型注册 ----
    model = AcadosModel()
    model.name = 'mars_landing_dyn'
    model.x = x_sym
    model.u = u_sym
    model.disc_dyn_expr = x_next
    ocp.model = model

    # ---- 维度 ----
    ocp.dims.nx = NX
    ocp.dims.nu = NU

    # ---- 代价: min Σ sigma_k (线性, 需要 EXACT Hessian) ----
    ocp.cost.cost_type = 'EXTERNAL'
    ocp.model.cost_expr_ext_cost   = sigma
    ocp.model.cost_expr_ext_cost_e = 0.0

    # ---- 非线性路径约束 h(x,u) <= 0 ----
    eps_sqrt = 1e-8
    h_expr = ca.vertcat(
        ca.sqrt(ux**2 + uy**2 + uz**2 + eps_sqrt) - sigma,
        ca.sqrt(ry**2 + rz**2 + eps_sqrt) - rx * tan_theta,
    )
    ocp.model.con_h_expr = h_expr
    nh = 2
    ocp.constraints.lh = np.full(nh, -1e9)
    ocp.constraints.uh = np.zeros(nh)

    # ---- 控制边界: sigma >= 0 ----
    ocp.constraints.lbu   = np.array([0.0])
    ocp.constraints.ubu   = np.array([1e9])
    ocp.constraints.idxbu = np.array([3])

    # ---- 初始状态 ----
    ocp.constraints.x0 = np.array([1500, 0, 2000, -75, 0, 100, np.log(m0)])

    # ---- 终端状态: r=0, v=0 (z 自由) ----
    ocp.constraints.idxbx_e = np.array([0, 1, 2, 3, 4, 5])
    ocp.constraints.lbx_e = np.zeros(6)
    ocp.constraints.ubx_e = np.zeros(6)

    # ---- 求解器选项 ----
    ocp.solver_options.qp_solver = 'FULL_CONDENSING_HPIPM'
    ocp.solver_options.hessian_approx = 'EXACT'
    ocp.solver_options.exact_hess_dyn = 1
    ocp.solver_options.exact_hess_cost = 1
    ocp.solver_options.exact_hess_constr = 1
    ocp.solver_options.integrator_type = 'DISCRETE'
    ocp.solver_options.nlp_solver_type = 'SQP'
    ocp.solver_options.nlp_solver_max_iter = 300
    ocp.solver_options.nlp_solver_tol_stat = 1e-4
    ocp.solver_options.nlp_solver_tol_eq   = 1e-4
    ocp.solver_options.nlp_solver_tol_ineq = 1e-4
    ocp.solver_options.nlp_solver_tol_comp = 1e-4
    ocp.solver_options.globalization = 'MERIT_BACKTRACKING'
    ocp.solver_options.alpha_min = 0.001
    ocp.solver_options.levenberg_marquardt = 1e-4
    ocp.solver_options.print_level = 0

    return ocp


# ========================== 求解函数 ==========================================

def solve_acados():
    """
    使用 acados SQP 求解火星着陆 NLP。

    返回: (fuel_used_kg, solver_name)
    返回 None 如果求解失败。
    """
    ocp = create_ocp()
    json_path = 'mars_acados.json'

    from acados_template import AcadosOcpSolver
    try:
        solver = AcadosOcpSolver(ocp, json_file=json_path,
                                  verbose=False, generate=True, build=True)
    except Exception as e:
        print(f"  acados SQP: 构建失败 ({e})")
        return None, "acados SQP"

    # 初始猜测
    x0_init = np.array([1500.0, 0.0, 2000.0, -75.0, 0.0, 100.0, np.log(m0)])
    xN_est  = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         np.log(m0 - 400.7)])  # ECOS 解作为质量猜测
    for k in range(N + 1):
        t = k / N
        solver.set(k, 'x', (1 - t) * x0_init + t * xN_est)
        if k < N:
            # 小推力初始猜测
            solver.set(k, 'u', np.array([4.0, 0.0, 0.0, 5.0]))

    status = solver.solve()

    x_N = solver.get(N, 'x')
    zf = float(x_N[6])
    fuel = m0 - np.exp(zf)

    status_msg = {0: 'OK', 1: 'MAXITER', 2: 'MAXITER', 3: 'QP_FAIL', 4: 'MINSTEP'}
    return fuel, f"acados SQP [{status_msg.get(status, '?')}]"


# ========================== 主程序 ============================================

if __name__ == '__main__':
    print("=" * 60)
    print("  火星着陆轨迹优化 — acados SQP (实验性)")
    print("=" * 60)
    print(f"  m0={m0:.0f}kg  N={N}  dt={dt:.1f}s  θ={np.degrees(theta):.1f}°")

    result = solve_acados()
    if result is not None:
        fuel, name = result
        ref = 400.7
        dev = (fuel - ref) / ref * 100
        print(f"  {name}: {fuel:.1f} kg ({dev:+.1f}%)")
        print(f"  基准 (ECOS SOCP): {ref} kg")
    print("=" * 60)
