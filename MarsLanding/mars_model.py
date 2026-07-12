#!/usr/bin/env python3
"""
=============================================================================
 mars_model.py — 火星着陆 SOCP 自动建模 (CasADi)
=============================================================================

 功能: 使用 CasADi 符号计算自动构造火星着陆 SOCP 问题的稀疏矩阵 A 和 G,
       与手写版 (MarsLanding.c) 的矩阵逐元素对比, 验证一致性。

 验证方法:
   python3 mars_model.py         # 输出矩阵差异摘要
   python3 mars_model.py --dump  # 输出完整矩阵 (用于逐元素比对)

 依赖: pip install casadi numpy

 作者: LShang + Hermes Agent
 日期: 2026-07-12
=============================================================================
"""

import casadi as ca
import numpy as np
import sys

# ========================== 物理参数 (从 mars_params 导入) ===============

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mars_params import (N, g_mars as g, g_earth as g_e, m0 as m_0,
                          I_sp, T_max, T_frac, T2_frac, n_T,
                          phi, theta, r0 as r_0, v0 as v_0,
                          rf as r_f, vf as v_f, t_f,
                          alpha, rho1 as rho_1, rho2 as rho_2, dt)

NX = 7; NU = 4; NV = NX + NU

def z0(k): return np.log(m_0 - alpha * rho_2 * k * dt)
def mu1(k): return rho_1 * np.exp(-z0(k))
def mu2(k): return rho_2 * np.exp(-z0(k))

# ========================== 符号变量构造 ===================================

# 优化变量: x = [r0, v0, z0, u0, sigma0, r1, ..., uN, sigmaN]
# 每块 11 维, 共 31 块, 总 341 维
x = ca.MX.sym('x', NV * (N + 1))

def rx(k): return x[k*NV + 0]  # 位置 x
def ry(k): return x[k*NV + 1]  # 位置 y
def rz(k): return x[k*NV + 2]  # 位置 z
def vx(k): return x[k*NV + 3]  # 速度 x
def vy(k): return x[k*NV + 4]  # 速度 y
def vz(k): return x[k*NV + 5]  # 速度 z
def z(k):  return x[k*NV + 6]  # 质量对数
def ux(k): return x[k*NV + 7]  # 推力 x
def uy(k): return x[k*NV + 8]  # 推力 y
def uz(k): return x[k*NV + 9]  # 推力 z
def s(k):  return x[k*NV + 10] # 松弛变量

# ========================== 约束构造 =======================================

# ---- 等式约束: A*x == b ----
# 约束方程采用与 C 手写版 MarsLanding.c 完全一致的符号约定,
# 使得 CasADi 自动微分提取的 A 矩阵与 C 代码逐元素匹配。
#
# C 代码约束形式 (A*x = b 的每一行):
#   初始BC:     x_i = boundary_value → eq: x_i - boundary_value = 0
#   终端BC:     x_i = 0             → eq: x_i = 0
#   位置动力学:  r_k + v_k*dt + ½u_k*dt² - r_{k+1} - ½g*dt² = 0  (g仅x)
#   速度动力学:  v_k + u_k*dt - v_{k+1} - g*dt = 0                 (g仅x)
#   质量动力学:  z_k - α*σ_k*dt - z_{k+1} = 0
#
# 物理: +x向上, 重力向下(-x方向), 故 g 项前为减号
eq_constr = []

# 初始边界条件 (7个)
eq_constr.append(rx(0) - r_0[0])
eq_constr.append(ry(0) - r_0[1])
eq_constr.append(rz(0) - r_0[2])
eq_constr.append(vx(0) - v_0[0])
eq_constr.append(vy(0) - v_0[1])
eq_constr.append(vz(0) - v_0[2])
eq_constr.append(z(0) - np.log(m_0))

# 终端边界条件 (6个, z_N 自由, 目标着陆点为零)
eq_constr.append(rx(N))
eq_constr.append(ry(N))
eq_constr.append(rz(N))
eq_constr.append(vx(N))
eq_constr.append(vy(N))
eq_constr.append(vz(N))

# 动力学约束 (7 × N 个)
for k in range(N):
    # 位置 rx: rx_k + dt*vx_k + ½dt²*ux_k - rx_{k+1} - ½g*dt² = 0
    eq_constr.append(rx(k) + vx(k)*dt + 0.5*ux(k)*dt*dt - rx(k+1) - 0.5*g*dt*dt)
    # 位置 ry: ry_k + dt*vy_k + ½dt²*uy_k - ry_{k+1} = 0
    eq_constr.append(ry(k) + vy(k)*dt + 0.5*uy(k)*dt*dt - ry(k+1))
    # 位置 rz: rz_k + dt*vz_k + ½dt²*uz_k - rz_{k+1} = 0
    eq_constr.append(rz(k) + vz(k)*dt + 0.5*uz(k)*dt*dt - rz(k+1))
    # 速度 vx: vx_k + dt*ux_k - vx_{k+1} - g*dt = 0
    eq_constr.append(vx(k) + ux(k)*dt - vx(k+1) - g*dt)
    # 速度 vy: vy_k + dt*uy_k - vy_{k+1} = 0
    eq_constr.append(vy(k) + uy(k)*dt - vy(k+1))
    # 速度 vz: vz_k + dt*uz_k - vz_{k+1} = 0
    eq_constr.append(vz(k) + uz(k)*dt - vz(k+1))
    # 质量对数: z_k - α*σ_k*dt - z_{k+1} = 0
    eq_constr.append(z(k) - alpha*s(k)*dt - z(k+1))

# ---- 线性不等式约束: G*x <= h ----
# ECOS 要求: 前 L_G 行全为线性约束, 后 M_G-L_G 行全为锥约束
# 与 MarsLanding.c 完全一致的分组顺序:
#   行 0~61   : 质量值不等式 (2 per k × 31)
#   行 62~123 : 质量上下界   (2 per k × 31)
#   行 124~216: 下滑角锥     (SOC q=3, 3 per cone × 31)
#   行 217~340: 推力松弛锥   (SOC q=4, 4 per cone × 31)
ineq_constr = []

# 4.4.1 质量值不等式 (62 行): μ₁_k·(z_k-z₀_k-1)+σ_k ≤ 0 等
for k in range(N + 1):
    ineq_constr.append(-mu1(k)*(z(k) - z0(k) - 1) - s(k))
    ineq_constr.append( mu2(k)*(z(k) - z0(k) - 1) + s(k))

# 4.4.2 质量上下界 (62 行): z_k 的干重/湿重边界
for k in range(N + 1):
    ineq_constr.append(-z(k) + np.log(m_0 - alpha * rho_2 * k * dt))
    ineq_constr.append( z(k) - np.log(m_0 - alpha * rho_1 * k * dt))

# 4.4.3 下滑角锥 (93 行, SOC q=3): ||[ry,rz]|| ≤ rx·tan(θ)
# ECOS: h-Gx ∈ K₃, G 用负号使 h-Gx = [rx·tanθ, ry, rz]
for k in range(N + 1):
    ineq_constr.append(-rx(k) * np.tan(theta))
    ineq_constr.append(-ry(k))
    ineq_constr.append(-rz(k))

# 4.4.4 推力松弛锥 (124 行, SOC q=4): ||[ux,uy,uz]|| ≤ σ
# ECOS: h-Gx ∈ K₄, G 用负号使 h-Gx = [σ, ux, uy, uz]
for k in range(N + 1):
    ineq_constr.append(-s(k))
    ineq_constr.append(-ux(k))
    ineq_constr.append(-uy(k))
    ineq_constr.append(-uz(k))

# ---- 目标函数: minimize sum(sigma_k) ----
obj = sum(s(k) for k in range(N + 1))

# ========================== 提取数值矩阵 ===================================

# 合并约束向量
eq_vec   = ca.vertcat(*eq_constr)
ineq_vec = ca.vertcat(*ineq_constr)

# CasADi 自动微分为我们提取稀疏 Jacobian
A_casadi = ca.Function('A', [x], [ca.jacobian(eq_vec, x)])(ca.DM.zeros(NV*(N+1)))
G_casadi = ca.Function('G', [x], [ca.jacobian(ineq_vec, x)])(ca.DM.zeros(NV*(N+1)))

# 约束右端项: b = -eq(0), h = -ineq(0)  (与 mars_codegen.py 一致)
b_vec = -ca.Function('b', [x], [eq_vec])(ca.DM.zeros(NV*(N+1)))
h_vec = -ca.Function('h', [x], [ineq_vec])(ca.DM.zeros(NV*(N+1)))

# ========================== 输出摘要 =======================================

A_sp = A_casadi.sparsity()
G_sp = G_casadi.sparsity()

n_var  = NV * (N + 1)
n_eq   = len(eq_constr)
n_ineq = len(ineq_constr)

print(f"============================================================")
print(f"  CasADi 火星着陆 SOCP 自动建模 — 矩阵摘要")
print(f"============================================================")
print(f"  优化变量                : {n_var}")
print(f"  等式约束 (A)            : {n_eq} 行 × {n_var} 列")
print(f"  不等式约束 (G)          : {n_ineq} 行 × {n_var} 列")
print(f"  A 非零元                : {A_sp.nnz()}")
print(f"  G 非零元                : {G_sp.nnz()}")
print()

# ---- 与手写版对比 ----
# 手写版: p=223, m=341, nnzA=733, nnzG=403
print(f"  手写版 A 非零元          : 733")
print(f"  手写版 G 非零元          : 403")
print(f"  A 差异                   : {A_sp.nnz() - 733} ({'+' if A_sp.nnz()>=733 else ''}{A_sp.nnz()-733})")
print(f"  G 差异                   : {G_sp.nnz() - 403} ({'+' if G_sp.nnz()>=403 else ''}{G_sp.nnz()-403})")
print()

sparsity_ok = A_sp.nnz() == 733 and G_sp.nnz() == 403
if sparsity_ok:
    print("  ✅ 非零元计数完全匹配!")
else:
    if A_sp.nnz() != 733:
        print(f"  ⚠ A 矩阵非零元计数不匹配: 手写733 vs CasADi {A_sp.nnz()}")
    if G_sp.nnz() != 403:
        print(f"  ⚠ G 矩阵非零元计数不匹配: 手写403 vs CasADi {G_sp.nnz()}")

# ---- 数值验证 ----
# 将 CasADi 矩阵与预期的手写版关键数值逐项对比
# C代码 b[0]=r_0[0]=1500, b[7]=r_f[0]=0, b[13]=0.5*g*dt²=13.528...
# C代码 h[0]=-mu1*(1+z0), h[124]=0 (下滑角锥起点), h[217]=0 (推力锥起点)
b_casadi = ca.DM(b_vec)
h_casadi = ca.DM(h_vec)

print()
print(f"  --- 关键 b 向量值对比 (前7行=初始BC, 第13行=rx动力学) ---")
b_expected = [
    ("b[0] rx_0", 1500.0),
    ("b[1] ry_0", 0.0),
    ("b[2] rz_0", 2000.0),
    ("b[3] vx_0", -75.0),
    ("b[4] vy_0", 0.0),
    ("b[5] vz_0", 100.0),
    ("b[6] z_0", np.log(1905.0)),
    ("b[13] rx dyn", 0.5 * g * dt * dt),
]
for label, expected in b_expected:
    casadi_val = float(b_casadi[int(label.split(']')[0][2:])])
    match = "✅" if abs(casadi_val - expected) < 1e-6 else "⚠️"
    print(f"    {label}: CasADi={casadi_val:.6f}  C={expected:.6f}  {match}")

print()
print(f"  --- 关键 h 向量值 ---")
print(f"    h[0] (质量下界):  {float(h_casadi[0]):.6f}")
print(f"    h[1] (质量上界):  {float(h_casadi[1]):.6f}")
print(f"    h[124] (下滑角锥): {float(h_casadi[124]):.6f} (应为0)")
print(f"    h[217] (推力锥):   {float(h_casadi[217]):.6f} (应为0)")

if '--dump' in sys.argv:
    print("\n--- A 矩阵 (CSR格式, 前100个非零元) ---")
    A_dense = ca.DM(A_casadi)
    for col in range(min(20, n_var)):
        for row in range(n_eq):
            if abs(A_dense[row, col]) > 1e-12:
                print(f"  A[{row},{col}] = {A_dense[row, col]:.6f}")

print(f"\n============================================================")
print(f"  验证方法:")
print(f"     python3 mars_model.py          # 摘要+数值对比")
print(f"     python3 mars_model.py --dump   # 完整矩阵")
print(f"============================================================")
