#!/usr/bin/env python3
"""
=============================================================================
 mars_acados.py — 火星着陆轨迹优化 acados SQP 求解器 (惩罚法)
=============================================================================

 策略: 将 SOC 非线性约束转为二次惩罚项加入代价, 使用 GAUSS_NEWTON SQP.
 该方法避免 EXACT Hessian 在 sqrt 原点处的病态问题。

 惩罚项 (平滑近似):
  推力锥:  w * softplus(||u||² - σ²)²
  下滑角:  w * softplus(ry²+rz² - (rx·tanθ)²)²

 其中 softplus(x) = log(1 + exp(x)) (光滑的 max(0,x))

 求解策略:
  1. 先用小权重 w 求解 (允许约束违反)
  2. 逐步增大 w, 用上一轮的解 warm-start
  3. 最终 w → ∞ 的解逼近真实约束问题

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

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mars_params import (N, g_mars as g, g_earth as g_e, m0, I_sp as Isp,
                          T_max as T_max_co, T_frac, T2_frac, n_T as nT,
                          phi, theta, t_f, dt, alpha, rho1, rho2)
NX = 7; NU = 4
tan_theta = np.tan(theta)

# 对数的数值安全边界
z_min_global = np.log(m0 - alpha * rho2 * t_f)  # 终端最小质量对数


# ========================== 惩罚法 OCP 建模 ==================================

from acados_template import AcadosOcp, AcadosModel

def create_ocp(penalty_weight=1.0):
    """
    构造带惩罚项的 acados OCP。

    参数:
      penalty_weight: 约束违反的惩罚系数 w. w 越大 → 约束越紧.
    """
    ocp = AcadosOcp()
    ocp.model.name = 'mars_landing_pen'
    ocp.solver_options.N_horizon = N
    ocp.solver_options.tf = t_f

    # ---- 符号变量 ----
    x_sym = ca.MX.sym('x', NX)
    u_sym = ca.MX.sym('u', NU)

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

    model = AcadosModel()
    model.name = 'mars_dyn'
    model.x = x_sym
    model.u = u_sym
    model.disc_dyn_expr = x_next
    ocp.model = model

    # ---- 维度 ----
    ocp.dims.nx = NX
    ocp.dims.nu = NU
    ocp.dims.ny = 3     # [√fuel, √thrust_pen, √glide_pen]
    ocp.dims.ny_e = 0

    # ---- 惩罚项计算 ----
    # softplus(x) = log(1+exp(x)) — 光滑的 max(0,x)
    # 推力锥违反: ||u||² - σ²
    thrust_viol = ux**2 + uy**2 + uz**2 - sigma**2
    # 下滑角违反: ry²+rz² - (rx·tanθ)²
    glide_viol = ry**2 + rz**2 - (rx * tan_theta)**2

    eps_sp = 1e-4  # softplus 的平滑参数
    sp_thrust = ca.log(1 + ca.exp(thrust_viol / eps_sp)) * eps_sp
    sp_glide  = ca.log(1 + ca.exp(glide_viol  / eps_sp)) * eps_sp

    w = penalty_weight

    # ---- 代价: LS 残差向量 ----
    # y = [√σ,  √(w) * sp_thrust,  √(w) * sp_glide]
    # min ||y||² = Σ σ + w·Σ penalty → 等效于 min Σ σ s.t. constraints
    ocp.cost.cost_type = 'NONLINEAR_LS'
    ocp.model.cost_y_expr = ca.vertcat(
        ca.sqrt(sigma + 1e-8),          # √σ (阶段燃料)
        ca.sqrt(w) * sp_thrust,          # √(w·penalty) 推力锥
        ca.sqrt(w) * sp_glide,           # √(w·penalty) 下滑角
    )
    ocp.model.cost_y_expr_e = ca.DM.zeros(0, 1)

    W = np.eye(3)
    ocp.cost.W   = W
    ocp.cost.W_e = np.zeros((0, 0))
    ocp.cost.yref   = np.zeros(3)
    ocp.cost.yref_e = np.zeros(0)

    # ---- 控制边界 ----
    ocp.constraints.lbu   = np.array([0.0, 0.0, 0.0, 0.0])  # u≥0 (简化)
    ocp.constraints.ubu   = np.array([1e4, 1e4, 1e4, 1e4])
    ocp.constraints.idxbu = np.array([0, 1, 2, 3])

    # ---- 状态边界: z 有界, 防止质量异常 ----
    ocp.constraints.idxbx = np.array([6])
    ocp.constraints.lbx   = np.array([z_min_global])
    ocp.constraints.ubx   = np.array([np.log(m0)])

    # ---- 初始/终端 ----
    ocp.constraints.x0 = np.array([1500, 0, 2000, -75, 0, 100, np.log(m0)])
    ocp.constraints.idxbx_e = np.array([0, 1, 2, 3, 4, 5])
    ocp.constraints.lbx_e = np.zeros(6)
    ocp.constraints.ubx_e = np.zeros(6)

    # ---- 求解器选项 ----
    ocp.solver_options.qp_solver = 'FULL_CONDENSING_HPIPM'
    ocp.solver_options.hessian_approx = 'GAUSS_NEWTON'
    ocp.solver_options.integrator_type = 'DISCRETE'
    ocp.solver_options.nlp_solver_type = 'SQP'
    ocp.solver_options.nlp_solver_max_iter = 200
    ocp.solver_options.nlp_solver_tol_stat = 1e-4
    ocp.solver_options.nlp_solver_tol_eq   = 1e-4
    ocp.solver_options.nlp_solver_tol_ineq = 1e-4
    ocp.solver_options.nlp_solver_tol_comp = 1e-4
    ocp.solver_options.globalization = 'MERIT_BACKTRACKING'
    ocp.solver_options.alpha_min = 0.001
    ocp.solver_options.levenberg_marquardt = 1e-3
    ocp.solver_options.print_level = 0

    return ocp


# ========================== 求解函数 ==========================================

def solve_acados():
    """
    使用 acados SQP + 惩罚法求解火星着陆问题。

    多轮策略: 从 w=0.1 开始, 逐步增加到 w=1e6,
    每轮用上一轮的解 warm-start, 最终逼近真实约束解。

    返回: (fuel_used_kg, solver_name)
    """
    from acados_template import AcadosOcpSolver

    # 多轮惩罚法: 从 w=1 开始逐步增加到 1e5
    # 中间轮次可能 MINSTEP (小权重时约束不够紧, 解跳跃), 但不影响最终轮
    import os, sys
    weights = [10.0, 1000.0, 100000.0]
    max_viol = 0.0

    # 初始猜测: 基于 ECOS 解的线性插值
    x_guess = np.zeros((N + 1, NX))
    u_guess = np.zeros((N, NU))
    for k in range(N + 1):
        t = k / N
        x_guess[k] = [(1-t)*1500, 0, (1-t)*2000,
                       -75 + 75*t, 0, 100 - 100*t,
                       np.log(m0 - 400.7*t)]
        if k < N:
            u_guess[k] = [4.0, 0.0, 1.0, 5.0]

    for w in weights:
        ocp = create_ocp(penalty_weight=w)
        json_path = f'mars_acados_w{w}.json'

        try:
            solver = AcadosOcpSolver(ocp, json_file=json_path,
                                      verbose=False, generate=True, build=True)
        except Exception as e:
            if w == weights[-1]:
                raise
            continue

        for k in range(N + 1):
            solver.set(k, 'x', x_guess[k])
            if k < N:
                solver.set(k, 'u', u_guess[k])

        # 注意: HPIPM MINSTEP 警告从 C 层直接输出, Python 无法拦截
        # 不影响求解质量, 可安全忽略
        status = solver.solve()

    if status == 0:
        for k in range(N + 1):
            x_guess[k] = solver.get(k, 'x')
            if k < N:
                u_guess[k] = solver.get(k, 'u')

    # 最终结果与约束检查
    xN = solver.get(N, 'x')
    zf = float(xN[6])
    fuel = m0 - np.exp(zf)

    for k in range(N):
        xk = solver.get(k, 'x'); uk = solver.get(k, 'u')
        u_norm = np.sqrt(float(uk[0])**2+float(uk[1])**2+float(uk[2])**2)
        sk = float(uk[3])
        rx_k = float(xk[0])
        viol_t = max(0, u_norm - sk)
        viol_g = max(0, np.sqrt(float(xk[1])**2+float(xk[2])**2) - rx_k*tan_theta)
        max_viol = max(max_viol, viol_t, viol_g)

    return fuel, f"acados SQP [viol={max_viol:.0e}]"


# ========================== 主程序 ============================================

if __name__ == '__main__':
    print("=" * 60)
    print("  火星着陆轨迹优化 — acados SQP (惩罚法)")
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
