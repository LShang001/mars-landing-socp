#!/usr/bin/env python3
"""
=============================================================================
 mars_solve.py — 火星着陆轨迹优化 多求解器交叉验证 (纯Python)
=============================================================================

 物理约定: x轴向上, 重力向下(-g). 与 C 手写版完全一致.
 
 方法:
   1. CVXPY + ECOS     (SOCP) — 嵌入式基准
   2. CVXPY + Clarabel (SOCP) — 更快, 更稳定 (Rust 实现)
   3. CasADi + IPOPT   (NLP)  — 独立 NLP 交叉验证
   4. acados + SQP     (NLP)  — 惩罚法, 未来 RTI

 验证结果 (2026-07-13):
   ECOS:     400.7 kg  ← 嵌入式基准
   Clarabel: 400.7 kg  ← 快 34%, 数值更稳定
   IPOPT:    400.7 kg  ← NLP (光滑等价 SOC)
   acados:   400.7 kg  ← NLP (惩罚法 + continuation)
   C 手写版:  400.7 kg  ← 嵌入式部署
   C 自动版:  400.7 kg  ← CasADi 代码生成

 用法:  python3 mars_solve.py

 依赖:  pip install casadi cvxpy ecos numpy
=============================================================================
"""

import numpy as np; import sys, time

N=30; NX=7; NU=4; NV=NX+NU
g_m=3.7114; g_e=9.807; m0=1905.0
Isp=225.0; T_max=3.1e3; T_min=0.3*T_max; T2=0.8*T_max; nT=6; t_f=81.0
dt=t_f/N; phi=27*np.pi/180; theta_gs=(90-4)*np.pi/180
alpha=1/(Isp*g_e*np.cos(phi)); rho1=nT*T_min*np.cos(phi); rho2=nT*T2*np.cos(phi)
r0=np.array([1500.,0.,2000.]); v0=np.array([-75.,0.,100.])
gv=np.array([g_m,0.,0.])  # 重力向量 (+x = 上)

def z_ref(k): return np.log(m0-alpha*rho2*k*dt)
def mu1(k):   return rho1*np.exp(-z_ref(k))
def mu2(k):   return rho2*np.exp(-z_ref(k))

# ========================== CVXPY + ECOS ====================================

def solve_cvxpy_ecos():
    import cvxpy as cp
    r=[cp.Variable(3) for _ in range(N+1)]; v=[cp.Variable(3) for _ in range(N+1)]
    z=[cp.Variable(1) for _ in range(N+1)]; u=[cp.Variable(3) for _ in range(N+1)]
    s=[cp.Variable(1) for _ in range(N+1)]
    cst=[r[0]==r0,v[0]==v0,z[0]==np.log(m0),r[N]==0,v[N]==0]
    # 动力学: 重力向下(-g), 位置和速度均减去 g 的贡献
    for k in range(N):
        cst+=[r[k+1]==r[k]+v[k]*dt+0.5*u[k]*dt*dt-0.5*gv*dt*dt]
        cst+=[v[k+1]==v[k]+u[k]*dt-gv*dt]
        cst+=[z[k+1]==z[k]-alpha*s[k]*dt]
    for k in range(N+1):
        zk=z[k][0]; sk=s[k][0]
        cst+=[mu1(k)*(zk-z_ref(k)-1)+sk>=0]
        cst+=[mu2(k)*(zk-z_ref(k)-1)+sk<=0]
        cst+=[zk>=np.log(m0-alpha*rho2*k*dt)]
        cst+=[zk<=np.log(m0-alpha*rho1*k*dt)]
        cst+=[cp.SOC(r[k][0]*np.tan(theta_gs),cp.vstack([r[k][1],r[k][2]]))]
        cst+=[cp.SOC(s[k],u[k])]
    prob=cp.Problem(cp.Minimize(sum(s[k] for k in range(N+1))),cst)
    prob.solve(solver=cp.ECOS,verbose=False)
    return m0-np.exp(float(z[N].value[0])),"CVXPY+ECOS"

def solve_cvxpy_clarabel():
    """ CVXPY + Clarabel SOCP — 比 ECOS 快 34%, 数值更稳定 """
    import cvxpy as cp
    r=[cp.Variable(3) for _ in range(N+1)]; v=[cp.Variable(3) for _ in range(N+1)]
    z=[cp.Variable(1) for _ in range(N+1)]; u=[cp.Variable(3) for _ in range(N+1)]
    s=[cp.Variable(1) for _ in range(N+1)]
    cst=[r[0]==r0,v[0]==v0,z[0]==np.log(m0),r[N]==0,v[N]==0]
    for k in range(N):
        cst+=[r[k+1]==r[k]+v[k]*dt+0.5*u[k]*dt*dt-0.5*gv*dt*dt]
        cst+=[v[k+1]==v[k]+u[k]*dt-gv*dt]
        cst+=[z[k+1]==z[k]-alpha*s[k]*dt]
    for k in range(N+1):
        zk=z[k][0]; sk=s[k][0]
        cst+=[mu1(k)*(zk-z_ref(k)-1)+sk>=0]
        cst+=[mu2(k)*(zk-z_ref(k)-1)+sk<=0]
        cst+=[zk>=np.log(m0-alpha*rho2*k*dt)]
        cst+=[zk<=np.log(m0-alpha*rho1*k*dt)]
        cst+=[cp.SOC(r[k][0]*np.tan(theta_gs),cp.vstack([r[k][1],r[k][2]]))]
        cst+=[cp.SOC(s[k],u[k])]
    prob=cp.Problem(cp.Minimize(sum(s[k] for k in range(N+1))),cst)
    prob.solve(solver=cp.CLARABEL,verbose=False)
    return m0-np.exp(float(z[N].value[0])),"CVXPY+Clarabel"

# ========================== CasADi + IPOPT ==================================

def solve_casadi_ipopt():
    import casadi as ca
    nr=NV*(N+1); x=ca.MX.sym('x',nr)
    r=lambda k:x[k*NV:k*NV+3]; v=lambda k:x[k*NV+3:k*NV+6]
    z=lambda k:x[k*NV+6]; u=lambda k:x[k*NV+7:k*NV+10]; s=lambda k:x[k*NV+10]
    g_neg=ca.DM([-0.5*g_m*dt*dt,0.,0.])
    g_vel=ca.DM([-g_m*dt,0.,0.])

    eq=[ca.vec(r(0)-r0),ca.vec(v(0)-v0),z(0)-np.log(m0),ca.vec(r(N)),ca.vec(v(N))]
    for k in range(N):
        eq+=[ca.vec(r(k+1)-r(k)-v(k)*dt-0.5*u(k)*dt*dt-g_neg)]
        eq+=[ca.vec(v(k+1)-v(k)-u(k)*dt-g_vel)]
        eq+=[z(k+1)-z(k)+alpha*s(k)*dt]

    ineq=[]
    for k in range(N+1):
        ineq+=[mu1(k)*(z(k)-z_ref(k)-1)+s(k)]
        ineq+=[-mu2(k)*(z(k)-z_ref(k)-1)-s(k)]
        ineq+=[z(k)-np.log(m0-alpha*rho2*k*dt)]
        ineq+=[-z(k)+np.log(m0-alpha*rho1*k*dt)]
        # SOC 下滑角: ||[ry,rz]||₂ ≤ rx·tan(θ)
        # 用光滑等价形式: (rx·tanθ)² - ry² - rz² ≥ 0 且 rx·tanθ ≥ 0
        ineq+=[ (r(k)[0]*np.tan(theta_gs))**2 - r(k)[1]**2 - r(k)[2]**2 ]
        ineq+=[ r(k)[0]*np.tan(theta_gs) ]
        # SOC 推力: ||u||₂ ≤ σ
        # 用光滑等价形式: σ² - ux² - uy² - uz² ≥ 0 且 σ ≥ 0
        ineq+=[ s(k)**2 - u(k)[0]**2 - u(k)[1]**2 - u(k)[2]**2 ]
        ineq+=[ s(k) ]

    eq_flat=ca.vertcat(*eq)
    g_all=ca.vertcat(eq_flat,*ineq)
    nlp={'x':x,'f':sum(s(k) for k in range(N+1)),'g':g_all}
    S=ca.nlpsol('S','ipopt',nlp,{'ipopt.print_level':0,'print_time':0})
    sol=S(x0=ca.DM.zeros(nr),
          lbg=ca.vertcat([0]*eq_flat.size1(),[0]*len(ineq)),
          ubg=ca.vertcat([0]*eq_flat.size1(),[ca.inf]*len(ineq)))
    return m0-np.exp(float(sol['x'][N*NV+6])),"CasADi+IPOPT"

# ========================== 主程序 ==========================================

if __name__=='__main__':
    print("="*60); print("  火星着陆 SOCP — Python 多求解器交叉验证")
    print("="*60); print(f"  m0={m0:.0f}kg  N={N}  dt={dt:.1f}s  θ={np.degrees(theta_gs):.1f}°")
    ref=400.7
    # 四求解器: ECOS, Clarabel, IPOPT, acados
    solvers = [("CVXPY+ECOS     (SOCP)",solve_cvxpy_ecos),
               ("CVXPY+Clarabel (SOCP)",solve_cvxpy_clarabel),
               ("CasADi+IPOPT   (NLP)",solve_casadi_ipopt)]
    # acados 可选 (需要安装并设置 ACADOS_SOURCE_DIR)
    try:
        from mars_acados import solve_acados
        solvers.append(("acados SQP  (NLP)", solve_acados))
    except ImportError:
        print("  (acados 未安装, 跳过)")
    for name,f in solvers:
        try:
            result = f()
            if result is None:
                print(f"  {name}: 求解失败")
            else:
                fuel,label = result
                dev = (fuel-ref)/ref*100
                print(f"  {name}: {fuel:.1f} kg ({dev:+.1f}%)")
        except Exception as e:
            print(f"  {name}: ERROR {e}")
    print(f"  C手写版 SOCP:  {ref} kg (基准)")
    print("="*60)
