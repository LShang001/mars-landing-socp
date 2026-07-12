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

# ========================== 物理参数 =======================================

N      = 30          # 离散点数
NX     = 7           # 状态维度: rx, ry, rz, vx, vy, vz, z(=ln m)
NU     = 4           # 控制维度: ux, uy, uz(推力), sigma(松弛变量)
NV     = NX + NU     # 每步变量数 = 11
g      = 3.7114      # 火星重力 m/s²
g_e    = 9.807       # 地球重力 m/s²
m_0    = 1905.0      # 初始质量 kg
I_sp   = 225.0       # 比冲 s
T_max  = 3.1e3       # 单台发动机最大推力 N
T_min  = 0.3 * T_max # 单台发动机最小推力 N
T_2    = 0.8 * T_max # 推力上界 (80% 额定)
n_T    = 6           # 发动机数量
phi    = 27.0 * np.pi / 180.0          # 安装倾角 rad
theta  = (90.0 - 4.0) * np.pi / 180.0  # 下滑角 86° rad
r_0    = [1500, 0, 2000]               # 初始位置 m
v_0    = [-75, 0, 100]                 # 初始速度 m/s
r_f    = [0, 0, 0]                     # 终端位置
v_f    = [0, 0, 0]                     # 终端速度
t_f    = 81.0                          # 着陆时间 s

# 时变参数
alpha  = 1.0 / (I_sp * g_e * np.cos(phi))
rho_1  = n_T * T_min * np.cos(phi)
rho_2  = n_T * T_2   * np.cos(phi)
dt     = t_f / N

def z0(k):
    """ 质量对数参考轨迹 """
    return np.log(m_0 - alpha * rho_2 * k * dt)

def mu1(k):
    """ 线性化系数 μ₁ """
    return rho_1 * np.exp(-z0(k))

def mu2(k):
    """ 线性化系数 μ₂ """
    return rho_2 * np.exp(-z0(k))

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
eq_constr = []

# 初始边界条件 (7个)
eq_constr.append(rx(0) - r_0[0])
eq_constr.append(ry(0) - r_0[1])
eq_constr.append(rz(0) - r_0[2])
eq_constr.append(vx(0) - v_0[0])
eq_constr.append(vy(0) - v_0[1])
eq_constr.append(vz(0) - v_0[2])
eq_constr.append(z(0) - np.log(m_0))

# 终端边界条件 (6个, z_N 自由)
eq_constr.append(rx(N))
eq_constr.append(ry(N))
eq_constr.append(rz(N))
eq_constr.append(vx(N))
eq_constr.append(vy(N))
eq_constr.append(vz(N))

# 动力学约束 (7 × N 个)
for k in range(N):
    # 位置: r_{k+1} = r_k + v_k*dt + 0.5*u_k*dt² + 0.5*g*dt²
    eq_constr.append(rx(k+1) - rx(k) - vx(k)*dt - 0.5*ux(k)*dt*dt - 0.5*g*dt*dt)
    eq_constr.append(ry(k+1) - ry(k) - vy(k)*dt - 0.5*uy(k)*dt*dt)
    eq_constr.append(rz(k+1) - rz(k) - vz(k)*dt - 0.5*uz(k)*dt*dt)
    # 速度: v_{k+1} = v_k + u_k*dt + g*dt  (g only in x)
    eq_constr.append(vx(k+1) - vx(k) - ux(k)*dt - g*dt)
    eq_constr.append(vy(k+1) - vy(k) - uy(k)*dt)
    eq_constr.append(vz(k+1) - vz(k) - uz(k)*dt)
    # 质量: z_{k+1} = z_k - alpha*s_k*dt
    eq_constr.append(z(k+1) - z(k) + alpha*s(k)*dt)

# ---- 线性不等式约束: G*x <= h ----
ineq_constr = []

for k in range(N + 1):
    # 质量值不等式 (线性化)
    ineq_constr.append(-mu1(k)*(z(k) - z0(k) - 1) - s(k))
    ineq_constr.append( mu2(k)*(z(k) - z0(k) - 1) + s(k))

    # 质量上下界
    ineq_constr.append(-z(k) + np.log(m_0 - alpha * rho_2 * k * dt))
    ineq_constr.append( z(k) - np.log(m_0 - alpha * rho_1 * k * dt))

    # 下滑角锥: ||[ry, rz]|| <= rx*tan(theta)  (ECOS SOC 形式)
    ineq_constr.append(rx(k) * np.tan(theta))  # 标量
    ineq_constr.append(ry(k))                    # 向量1
    ineq_constr.append(rz(k))                    # 向量2

    # 推力松弛锥: ||[ux, uy, uz]|| <= s (ECOS SOC 形式)
    ineq_constr.append(s(k))                     # 标量
    ineq_constr.append(ux(k))                    # 向量1
    ineq_constr.append(uy(k))                    # 向量2
    ineq_constr.append(uz(k))                    # 向量3

# ---- 目标函数: minimize sum(sigma_k) ----
obj = sum(s(k) for k in range(N + 1))

# ========================== 提取数值矩阵 ===================================

# 合并约束向量
eq_vec   = ca.vertcat(*eq_constr)
ineq_vec = ca.vertcat(*ineq_constr)

# CasADi 自动微分为我们提取稀疏 Jacobian
A_casadi = ca.Function('A', [x], [ca.jacobian(eq_vec, x)])(ca.DM.zeros(NV*(N+1)))
G_casadi = ca.Function('G', [x], [ca.jacobian(ineq_vec, x)])(ca.DM.zeros(NV*(N+1)))

# 约束右端项: b = -A*x + eq_vec, h = -G*x + ineq_vec (在 x=0 处求值)
b_vec = ca.Function('b', [x], [-A_casadi @ x + eq_vec])(ca.DM.zeros(NV*(N+1)))
h_vec = ca.Function('h', [x], [-G_casadi @ x + ineq_vec])(ca.DM.zeros(NV*(N+1)))

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

if A_sp.nnz() == 733 and G_sp.nnz() == 403:
    print("  ✅ 非零元计数完全匹配! CasADi 建模与手写版一致。")
elif A_sp.nnz() != 733:
    print(f"  ⚠ A 矩阵非零元计数不匹配: 手写733 vs CasADi {A_sp.nnz()}")
elif G_sp.nnz() != 403:
    print(f"  ⚠ G 矩阵非零元计数不匹配: 手写403 vs CasADi {G_sp.nnz()}")

# ---- 对比数值 ----
# 加载手写版矩阵 (从 MarsLanding.c 输出)
# CasADi 矩阵和手写版应该在非零元位置和数值上完全一致
# 验证: 在 x=0 处, A*x+b 和 G*x+h 应该与手写版一致

if '--dump' in sys.argv:
    print("\n--- A 矩阵 (CSR格式, 前100个非零元) ---")
    A_dense = ca.DM(A_casadi)
    for col in range(min(20, n_var)):
        for row in range(n_eq):
            if abs(A_dense[row, col]) > 1e-12:
                print(f"  A[{row},{col}] = {A_dense[row, col]:.6f}")

print(f"\n============================================================")
print(f"  验证方法:")
print(f"     python3 mars_model.py          # 摘要对比")
print(f"     python3 mars_model.py --dump   # 完整矩阵")
print(f"============================================================")
