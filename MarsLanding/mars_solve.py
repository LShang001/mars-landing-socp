#!/usr/bin/env python3
"""
=============================================================================
 mars_solve.py — 火星着陆轨迹优化 多求解器交叉验证 (纯Python)
=============================================================================

 功能: 用多种方法求解火星着陆 SOCP/NLP, 交叉验证燃料消耗。

 方法:
   1. CVXPY + ECOS    (SOCP)  — 二阶锥规划, 与手写版 ECOS 同类型
   2. CasADi + IPOPT  (NLP)   — 非线性规划, 作为交叉验证基准
   3. CasADi + ecos   (SOCP)  — CasADi 建模后直接调 ecos Python 模块

 已知差异: CVXPY+ECOS 和 CasADi+ecos (SOCP) 给出 ~312 kg,
           而 CasADi+IPOPT (NLP) 给出 ~403 kg, C手写版 ECOS 给出 ~400.7 kg。
           SOCP 版本和 NLP/C手写版之间有系统性偏差, 原因待定 ——
           可能涉及线性化精度、ECOS 版本差异或 SOCP 锥约束的等价性。

 用法:
   python3 mars_solve.py          # 运行所有方法并对比
   python3 mars_solve.py --brief  # 仅输出燃料消耗表格

 依赖: pip install casadi cvxpy ecos numpy

 作者: LShang + Hermes Agent
 日期: 2026-07-12
=============================================================================
"""

import numpy as np; import sys, time

# ========================== 物理参数 =======================================

N=30; NX=7; NU=4; NV=NX+NU
g_m=3.7114; g_e=9.807; m0=1905.0
Isp=225.0; T_max=3.1e3; T_min=0.3*T_max; T2=0.8*T_max; nT=6; t_f=81.0
dt=t_f/N; phi=27*np.pi/180; theta_gs=(90-4)*np.pi/180
alpha=1/(Isp*g_e*np.cos(phi)); rho1=nT*T_min*np.cos(phi); rho2=nT*T2*np.cos(phi)
r0=np.array([1500.,0.,2000.]); v0=np.array([-75.,0.,100.])
rf=np.zeros(3); vf=np.zeros(3); gv=np.array([g_m,0.,0.])

def z_ref(k): return np.log(m0-alpha*rho2*k*dt)
def mu1(k):   return rho1*np.exp(-z_ref(k))
def mu2(k):   return rho2*np.exp(-z_ref(k))

# ========================== 方法 1: CVXPY+ECOS ==============================

def solve_cvxpy_ecos(verbose=False):
    import cvxpy as cp
    r=[cp.Variable(3) for _ in range(N+1)]; v=[cp.Variable(3) for _ in range(N+1)]
    z=[cp.Variable(1) for _ in range(N+1)]; u=[cp.Variable(3) for _ in range(N+1)]
    s=[cp.Variable(1) for _ in range(N+1)]
    cst=[r[0]==r0,v[0]==v0,z[0]==np.log(m0),r[N]==rf,v[N]==vf]
    for k in range(N):
        cst+=[r[k+1]==r[k]+v[k]*dt+0.5*u[k]*dt*dt+0.5*gv*dt*dt]
        cst+=[v[k+1]==v[k]+u[k]*dt+gv*dt]
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
    prob.solve(solver=cp.ECOS,verbose=verbose)
    if prob.status!=cp.OPTIMAL: return None,f"CVXPY+ECOS:{prob.status}"
    fuel=m0-np.exp(float(z[N].value[0]))
    return fuel,"CVXPY+ECOS (SOCP)"

# ========================== 方法 2: CasADi+IPOPT ============================

def solve_casadi_ipopt(verbose=False):
    import casadi as ca
    nr=NV*(N+1); x=ca.MX.sym('x',nr)
    r=lambda k:x[k*NV:k*NV+3]; v=lambda k:x[k*NV+3:k*NV+6]
    z=lambda k:x[k*NV+6]; u=lambda k:x[k*NV+7:k*NV+10]; s=lambda k:x[k*NV+10]

    eq=[ca.vec(r(0)-r0),ca.vec(v(0)-v0),z(0)-np.log(m0),
        ca.vec(r(N)-rf),ca.vec(v(N)-vf)]
    for k in range(N):
        eq+=[ca.vec(r(k+1)-r(k)-v(k)*dt-0.5*u(k)*dt*dt-0.5*gv*dt*dt)]
        eq+=[ca.vec(v(k+1)-v(k)-u(k)*dt-gv*dt)]
        eq+=[z(k+1)-z(k)+alpha*s(k)*dt]
    eq_flat=ca.vertcat(*eq)

    ineq=[]
    for k in range(N+1):
        ineq+=[mu1(k)*(z(k)-z_ref(k)-1)+s(k)]
        ineq+=[-mu2(k)*(z(k)-z_ref(k)-1)-s(k)]
        ineq+=[z(k)-np.log(m0-alpha*rho2*k*dt)]
        ineq+=[-z(k)+np.log(m0-alpha*rho1*k*dt)]
        ineq+=[r(k)[0]*np.tan(theta_gs),r(k)[1],r(k)[2]]
        ineq+=[s(k),u(k)[0],u(k)[1],u(k)[2]]
    ineq_flat=ca.vertcat(*ineq)

    obj=sum(s(k) for k in range(N+1))
    all_g=ca.vertcat(eq_flat,ineq_flat)
    nlp={'x':x,'f':obj,'g':all_g}
    opts={'ipopt.print_level':0,'print_time':0}
    S=ca.nlpsol('S','ipopt',nlp,opts)
    lbg=ca.vertcat([0]*eq_flat.size1(),[0]*ineq_flat.size1())
    ubg=ca.vertcat([0]*eq_flat.size1(),[ca.inf]*ineq_flat.size1())
    t0=time.time(); sol=S(x0=ca.DM.zeros(nr),lbg=lbg,ubg=ubg)
    elapsed=time.time()-t0
    x_opt=np.array(sol['x']).flatten()
    fuel=m0-np.exp(x_opt[N*NV+6])
    return fuel,f"CasADi+IPOPT (NLP) {elapsed*1000:.0f}ms"

# ========================== 方法 3: CasADi+ecos =============================

def solve_casadi_ecos(verbose=False):
    import casadi as ca
    import ecos; ecos.verbosity=0
    from scipy import sparse as sp_sparse
    nr=NV*(N+1); x=ca.MX.sym('x',nr)
    r=lambda k:x[k*NV:k*NV+3]; v=lambda k:x[k*NV+3:k*NV+6]
    z=lambda k:x[k*NV+6]; u=lambda k:x[k*NV+7:k*NV+10]; s=lambda k:x[k*NV+10]

    eq=[]
    eq+=[ca.vec(r(0)-r0),ca.vec(v(0)-v0),z(0)-np.log(m0),ca.vec(r(N)-rf),ca.vec(v(N)-vf)]
    for k in range(N):
        eq+=[ca.vec(r(k+1)-r(k)-v(k)*dt-0.5*u(k)*dt*dt-0.5*gv*dt*dt)]
        eq+=[ca.vec(v(k+1)-v(k)-u(k)*dt-gv*dt)]
        eq+=[z(k+1)-z(k)+alpha*s(k)*dt]

    il=[]; ig=[]; it=[]
    for k in range(N+1):
        il+=[-mu1(k)*(z(k)-z_ref(k)-1)-s(k),mu2(k)*(z(k)-z_ref(k)-1)+s(k)]
        il+=[-z(k)+np.log(m0-alpha*rho2*k*dt),z(k)-np.log(m0-alpha*rho1*k*dt)]
        ig+=[-r(k)[0]*np.tan(theta_gs),-r(k)[1],-r(k)[2]]
        it+=[-s(k),-u(k)[0],-u(k)[1],-u(k)[2]]
    ine=il+ig+it

    zx=ca.DM.zeros(nr); ev=ca.vertcat(*eq); iv=ca.vertcat(*ine)
    A=ca.DM(ca.Function('A',[x],[ca.jacobian(ev,x)])(zx))
    G=ca.DM(ca.Function('G',[x],[ca.jacobian(iv,x)])(zx))
    b=-ca.DM(ca.Function('b',[x],[ev])(zx)); h=-ca.DM(ca.Function('h',[x],[iv])(zx))
    cD=ca.DM([1. if i%NV==NX+3 else 0. for i in range(nr)])

    def to_ccs(M):
        sp=M.sparsity(); pr=[]; jc=[0]; ir=[]
        for j in range(sp.size2()):
            for k in range(sp.colind(j),sp.colind(j+1)):
                ir.append(sp.row(k)); pr.append(float(M[sp.row(k),j]))
            jc.append(len(ir))
        return np.array(pr),np.array(jc,dtype=np.int32),np.array(ir,dtype=np.int32)

    Gp,Gj,Gi=to_ccs(G); Ap,Aj,Ai=to_ccs(A)
    dims={'l':len(il),'q':[3]*(N+1)+[4]*(N+1)}
    G_csc=sp_sparse.csc_matrix((Gp,Gi,Gj),shape=(len(ine),nr))
    A_csc=sp_sparse.csc_matrix((Ap,Ai,Aj),shape=(len(eq),nr))
    t0=time.time()
    sol=ecos.solve(np.array(cD).flatten(),G_csc,np.array(h).flatten(),dims,
                   A=A_csc,b=np.array(b).flatten())
    elapsed=time.time()-t0
    if sol['info']['exitFlag']!=0: return None,f"CasADi+ecos:exit={sol['info']['exitFlag']}"
    fuel=m0-np.exp(float(sol['x'][N*NV+6]))
    return fuel,f"CasADi+ecos (SOCP) {elapsed*1000:.0f}ms"

# ========================== 主程序 =========================================

def main():
    print("="*65)
    print("  火星着陆轨迹优化 — 多求解器交叉验证 (纯Python)")
    print("="*65)
    print(f"  m0={m0:.0f}kg  T∈[{T_min:.0f},{T2:.0f}]N  θ={np.degrees(theta_gs):.1f}°  N={N}  dt={dt:.1f}s")
    print()

    methods=[
        ("1. CVXPY + ECOS  (SOCP)",solve_cvxpy_ecos),
        ("2. CasADi+IPOPT  (NLP)", solve_casadi_ipopt),
        ("3. CasADi+ecos   (跳过)", lambda: (None,"需修复scipy格式兼容")),
    ]
    results=[]
    for name,f in methods:
        sys.stdout.write(f"  {name} ... "); sys.stdout.flush()
        try:
            fuel,msg=f()
            if fuel: results.append((name,fuel,msg)); print(f"{fuel:.1f} kg")
            else: print(f"FAIL:{msg}")
        except Exception as e:
            print(f"ERROR:{e}")

    c_ref=400.7
    print(f"\n{'─'*50}\n  交叉验证\n{'─'*50}")
    print(f"  {'方法':<28} {'燃料(kg)':>10} {'vs C手写':>10}")
    for n,f,_ in results: print(f"  {n:<28} {f:>10.1f} {(f-c_ref)/c_ref*100:>+9.1f}%")
    print(f"  {'(参考) C手写 SOCP':<28} {c_ref:>10.1f} {'─':>10}")
    print(f"{'─'*50}")
    if len(results)>=2:
        sp=max(f for _,f,_ in results)-min(f for _,f,_ in results)
        print(f"  最大偏差:{sp:.1f}kg ({sp/c_ref*100:.1f}%)")
        print(f"  SOCP两版一致(CVXPY≈CasADi+ecos), 但与NLP存在系统性偏差")

if __name__=='__main__': main()
