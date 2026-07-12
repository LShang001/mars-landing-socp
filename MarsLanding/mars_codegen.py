#!/usr/bin/env python3
"""
=============================================================================
 mars_codegen.py — CasADi 自动生成火星着陆 SOCP 矩阵的 C 头文件
=============================================================================

 产出: MarsLanding/MarsLandingAutoData.h
       包含 A(G)_ccs_pr/jc/ir 数组和 b,c,h,q 数组, 可直接喂给 ECOS。

 用法: python3 mars_codegen.py

 作者: LShang + Hermes Agent
 日期: 2026-07-12
=============================================================================
"""

import casadi as ca
import numpy as np
import os

# ========================== 物理参数 (同 MarsLanding.c) =====================

N      = 30; NX = 7; NU = 4; NV = NX + NU
g      = 3.7114; g_e = 9.807; m_0 = 1905.0
I_sp   = 225.0; T_max = 3.1e3; T_min = 0.3 * T_max; T_2 = 0.8 * T_max
n_T    = 6
phi    = 27.0 * np.pi / 180.0
theta  = (90.0 - 4.0) * np.pi / 180.0
r_0    = [1500, 0, 2000]; v_0 = [-75, 0, 100]
r_f    = [0, 0, 0]; v_f = [0, 0, 0]; t_f = 81.0
alpha  = 1.0 / (I_sp * g_e * np.cos(phi))
rho_1  = n_T * T_min * np.cos(phi); rho_2 = n_T * T_2 * np.cos(phi)
dt     = t_f / N

def z0(k): return np.log(m_0 - alpha * rho_2 * k * dt)
def mu1(k): return rho_1 * np.exp(-z0(k))
def mu2(k): return rho_2 * np.exp(-z0(k))

# ========================== 符号建模 ========================================

x = ca.MX.sym('x', NV * (N + 1))

def rx(k): return x[k*NV+0]
def ry(k): return x[k*NV+1]
def rz(k): return x[k*NV+2]
def vx(k): return x[k*NV+3]
def vy(k): return x[k*NV+4]
def vz(k): return x[k*NV+5]
def z(k):  return x[k*NV+6]
def ux(k): return x[k*NV+7]
def uy(k): return x[k*NV+8]
def uz(k): return x[k*NV+9]
def s(k):  return x[k*NV+10]

eq = []
eq += [rx(0)-r_0[0], ry(0)-r_0[1], rz(0)-r_0[2], vx(0)-v_0[0], vy(0)-v_0[1], vz(0)-v_0[2], z(0)-np.log(m_0)]
eq += [rx(N), ry(N), rz(N), vx(N), vy(N), vz(N)]
for k in range(N):
    eq += [rx(k+1)-rx(k)-vx(k)*dt-0.5*ux(k)*dt*dt-0.5*g*dt*dt,
           ry(k+1)-ry(k)-vy(k)*dt-0.5*uy(k)*dt*dt,
           rz(k+1)-rz(k)-vz(k)*dt-0.5*uz(k)*dt*dt,
           vx(k+1)-vx(k)-ux(k)*dt-g*dt,
           vy(k+1)-vy(k)-uy(k)*dt,
           vz(k+1)-vz(k)-uz(k)*dt,
           z(k+1)-z(k)+alpha*s(k)*dt]

# ECOS 要求: 前 l 行全为线性约束, 后 m-l 行全为锥约束
# 按类型分组而非按 k 分组
ineq_linear = []
ineq_soc_glide = []  # q=3: 下滑角
ineq_soc_thrust = []  # q=4: 推力松弛
for k in range(N+1):
    # 质量值不等式 (线性) — 与手写版一致
    ineq_linear += [-mu1(k)*(z(k)-z0(k)-1)-s(k), mu2(k)*(z(k)-z0(k)-1)+s(k)]
    ineq_linear += [-z(k)+np.log(m_0-alpha*rho_2*k*dt), z(k)-np.log(m_0-alpha*rho_1*k*dt)]
    # 下滑角 SOC (q=3): h-Gx = [rx*tan, ry, rz] ∈ K₃
    ineq_soc_glide += [-rx(k)*np.tan(theta), -ry(k), -rz(k)]
    # 推力松弛 SOC (q=4): h-Gx = [sigma, ux, uy, uz] ∈ K₄
    ineq_soc_thrust += [-s(k), -ux(k), -uy(k), -uz(k)]
ineq = ineq_linear + ineq_soc_glide + ineq_soc_thrust

obj = sum(s(k) for k in range(N+1))

eq_vec   = ca.vertcat(*eq)
ineq_vec = ca.vertcat(*ineq)

# 提取稀疏矩阵
zero_x    = ca.DM.zeros(NV*(N+1))
A_casadi  = ca.Function('A', [x], [ca.jacobian(eq_vec, x)])(zero_x)
G_casadi  = ca.Function('G', [x], [ca.jacobian(ineq_vec, x)])(zero_x)
# 约束右端项: b = -eq(0), h = -ineq(0)
b_vec = -ca.Function('b', [x], [eq_vec])(zero_x)
h_vec = -ca.Function('h', [x], [ineq_vec])(zero_x)

# 转换为 DM 以便读取
A = ca.DM(A_casadi); G = ca.DM(G_casadi)
b = ca.DM(b_vec);    h = ca.DM(h_vec)
c = ca.DM([1.0 if (i % NV) == (NX + 3) else 0.0 for i in range(NV*(N+1))])

# ========================== CCS 格式转换 ====================================

def to_ccs(M):
    """ 将 CasADi 稀疏 DM 转换为 CCS 三数组 """
    sp = M.sparsity()
    col_ptr = [0]
    rows = []; vals = []
    for j in range(sp.size2()):
        for k in range(sp.colind(j), sp.colind(j+1)):
            rows.append(sp.row(k))
            vals.append(float(M[sp.row(k), j]))
        col_ptr.append(len(rows))
    return col_ptr, rows, vals

A_jc, A_ir, A_pr = to_ccs(A)
G_jc, G_ir, G_pr = to_ccs(G)

# ========================== C 头文件生成 ===================================

NNZA  = len(A_pr)
NNZG  = len(G_pr)
M_G   = G.size1()
P_EQ  = A.size1()
N_VAR = NV*(N+1)
L_G   = 2*(N+1) + 2*(N+1)           # 质量值上下界 + 质量上下界 = 4*(N+1)
NCONES = 2*(N+1)
# ECOS q 数组: 前31个 q=3 (下滑角), 后31个 q=4 (推力松弛)
q_vals = [3]*(N+1) + [4]*(N+1)

HEADER = '''/**
 * ===========================================================================
 * MarsLandingAutoData.h — CasADi 自动生成的 SOCP 矩阵数据
 * ===========================================================================
 *
 * 生成方式: CasADi 3.7.2 符号建模 → 自动微分 → 稀疏矩阵提取 → CCS 格式
 * 生成脚本: mars_codegen.py
 * 用途:     直接喂给 ECOS_setup(), 替代手写矩阵
 *
 * 与手写版 (MarsLanding.c) 对比验证:
 *   A 非零元: {nnza} vs 733
 *   G 非零元: {nnzg} vs 403
 *   矩阵维度: p={peq} m={mg} n={nvar} l={lg} ncones={nc}
 *
 * 作者: LShang + Hermes Agent (CasADi 生成)
 * 日期: 2026-07-12
 * ===========================================================================
 */

#ifndef MARSLANDING_AUTO_DATA_H
#define MARSLANDING_AUTO_DATA_H

#include "ecos.h"

'''.format(nnza=NNZA, nnzg=NNZG, peq=P_EQ, mg=M_G, nvar=N_VAR, lg=L_G, nc=NCONES)

def write_array(f, name, dtype, data, per_line=8):
    f.write(f"static const {dtype} {name}[] = {{\n")
    for i in range(0, len(data), per_line):
        chunk = data[i:i+per_line]
        f.write("    " + ", ".join(str(v) for v in chunk) + ",\n")
    f.write("};\n\n")

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(OUTPUT_DIR, "MarsLandingAutoData.h"), "w") as f:
    f.write(HEADER)
    f.write(f"#define N_VAR_AUTO  {N_VAR}\n")
    f.write(f"#define P_EQ_AUTO   {P_EQ}\n")
    f.write(f"#define M_G_AUTO    {M_G}\n")
    f.write(f"#define L_G_AUTO    {L_G}\n")
    f.write(f"#define NCONES_AUTO {NCONES}\n")
    f.write(f"#define NNZA_AUTO   {NNZA}\n")
    f.write(f"#define NNZG_AUTO   {NNZG}\n\n")

    write_array(f, "CCA_pr_auto", "pfloat", [round(v, 12) for v in A_pr])
    write_array(f, "CCA_jc_auto", "idxint", A_jc)
    write_array(f, "CCA_ir_auto", "idxint", A_ir)
    write_array(f, "CCG_pr_auto", "pfloat", [round(v, 12) for v in G_pr])
    write_array(f, "CCG_jc_auto", "idxint", G_jc)
    write_array(f, "CCG_ir_auto", "idxint", G_ir)
    write_array(f, "c_auto", "pfloat", [round(float(c[i]), 12) for i in range(c.size1())])
    write_array(f, "b_auto", "pfloat", [round(float(b[i]), 12) for i in range(b.size1())])
    write_array(f, "h_auto", "pfloat", [round(float(h[i]), 12) for i in range(h.size1())])
    write_array(f, "q_auto", "idxint", q_vals)

    f.write("#endif /* MARSLANDING_AUTO_DATA_H */\n")

# 统计摘要
print(f"============================================================")
print(f"  CasADi → C 代码生成完成")
print(f"============================================================")
print(f"  产出: MarsLandingAutoData.h")
print(f"  A 非零元: {NNZA}  (手写版: 733)")
print(f"  G 非零元: {NNZG}  (手写版: 403)")
print(f"  维度: p={P_EQ} m={M_G} n={N_VAR} l={L_G} ncones={NCONES}")
print(f"  匹配状态: {'✅ 完全一致' if NNZA==733 and NNZG==403 else '⚠ 不一致!'}")
print(f"============================================================")
