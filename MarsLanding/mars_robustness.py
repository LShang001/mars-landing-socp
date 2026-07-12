#!/usr/bin/env python3
"""
=============================================================================
 mars_robustness.py — 火星着陆求解器鲁棒性测试 + 灵敏度分析
=============================================================================

 测试内容:
   1. Monte Carlo: 1000 组随机初始条件, 统计求解成功率和燃料分布
   2. 灵敏度: 逐个参数 ±1%, 计算 d(fuel)/d(param)

 用法:  python3 mars_robustness.py          # 快速版 (100 组)
       python3 mars_robustness.py --full   # 完整版 (1000 组)
       python3 mars_robustness.py --sens   # 仅灵敏度分析

 作者: LShang + Claude
 日期: 2026-07-13
=============================================================================
"""

import numpy as np
import sys, time
import cvxpy as cp

N=30; NX=7; NU=4; NV=NX+NU
g_m=3.7114; g_e=9.807; m0=1905.0
Isp=225.0; T_max=3.1e3; T_frac=0.3; T2_frac=0.8; nT=6
t_f=81.0; dt=t_f/N; phi=27*np.pi/180; theta_gs=(90-4)*np.pi/180
alpha=1/(Isp*g_e*np.cos(phi))
T_min=T_frac*T_max; T2=T2_frac*T_max
rho1=nT*T_min*np.cos(phi); rho2=nT*T2*np.cos(phi)
gv=np.array([g_m,0.,0.]); v0_nom=np.array([-75.,0.,100.])
r0_nom=np.array([1500.,0.,2000.])

def z_ref(k): return np.log(m0-alpha*rho2*k*dt)
def mu1(k): return rho1*np.exp(-z_ref(k))
def mu2(k): return rho2*np.exp(-z_ref(k))

def solve_one(r0,v0,verbose=False):
    """求解单个场景, 返回 (fuel, success)"""
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
        cst+=[cp.SOC(sk,u[k])]
    prob=cp.Problem(cp.Minimize(sum(s[k] for k in range(N+1))),cst)
    try:
        prob.solve(solver=cp.ECOS,verbose=False)
        if prob.status=='optimal':
            return m0-np.exp(float(z[N].value[0])), True
    except:
        pass
    return None, False


# ======================== Monte Carlo ========================================

def monte_carlo(n_samples=100):
    """随机采样初始条件, 统计成功率"""
    print(f"\n{'='*60}")
    print(f"  Monte Carlo 鲁棒性测试 ({n_samples} 组)")
    print(f"{'='*60}")

    rng=np.random.RandomState(42)
    # 采样范围: 基准值 ±50%, 速度 ±100%
    rx_range=[500,3000]; rz_range=[500,3000]
    vx_range=[-150,0]; vz_range=[0,200]

    fuels=[]; failures=0; t0=time.perf_counter()
    for i in range(n_samples):
        r0=np.array([rng.uniform(*rx_range),0,rng.uniform(*rz_range)])
        v0=np.array([rng.uniform(*vx_range),0,rng.uniform(*vz_range)])
        fuel, ok = solve_one(r0,v0)
        if ok: fuels.append(fuel)
        else: failures+=1
        if (i+1)%max(1,n_samples//10)==0:
            print(f"  {i+1}/{n_samples}...")

    t1=time.perf_counter()
    fuels=np.array(fuels)
    rate=100*(1-failures/n_samples)

    print(f"\n  结果:")
    print(f"    成功率: {rate:.1f}% ({n_samples-failures}/{n_samples})")
    print(f"    燃料: mean={np.mean(fuels):.1f} std={np.std(fuels):.1f} "
          f"min={np.min(fuels):.1f} max={np.max(fuels):.1f} kg")
    print(f"    基准: 400.7 kg")
    print(f"    耗时: {t1-t0:.1f}s ({1000*(t1-t0)/n_samples:.0f}ms/组)")

    # 失败案例分析
    if failures>0:
        print(f"\n  失败案例 ({failures}):")
        rng2=np.random.RandomState(42)
        for i in range(min(failures,5)):
            rng2.uniform(*rx_range); rng2.uniform(*rx_range)
            rng2.uniform(*vx_range); rng2.uniform(*vx_range)

    return rate, np.mean(fuels) if len(fuels)>0 else 0


# ======================== Sensitivity ========================================

def sensitivity():
    """逐个参数 ±1%, 计算灵敏度"""
    print(f"\n{'='*60}")
    print(f"  灵敏度分析 (参数 ±1%)")
    print(f"{'='*60}")

    r0=np.array([1500.,0.,2000.])
    v0=np.array([-75.,0.,100.])

    # 基准
    base_fuel, _ = solve_one(r0,v0)
    print(f"  基准燃料: {base_fuel:.2f} kg\n")

    # 可调参数列表
    params_global = {
        'm0': 1905.0,
        'Isp': 225.0,
        'T_max': 3.1e3,
        'T_frac': 0.3,
        'T2_frac': 0.8,
        'nT': 6,
        'phi_deg': 27.0,
        'theta_deg': 86.0,
        't_f': 81.0,
        'g_mars': 3.7114,
        'N': 30,
    }

    results=[]
    for name,nominal in params_global.items():
        # 需要 rebuild 全局变量
        global alpha,rho1,rho2,dt,gv,N_val,T_min,T2
        for delta_pct,label in [(-1,"-1%"),(1,"+1%")]:
            new_val=nominal*(1+delta_pct/100)
            # 局部修改并重算
            try:
                fuel=eval_sensitivity(name,new_val,r0,v0)
                if fuel:
                    sens=(fuel-base_fuel)/(delta_pct/100*nominal)
                    results.append((name,label,nominal,new_val,fuel,sens))
            except:
                pass

    # 排序输出
    print(f"  {'参数':12s} {'名义值':>10s} {'±1%':>6s} {'燃料':>8s} {'灵敏度':>10s}")
    print(f"  {'-'*50}")
    # 按灵敏度绝对值排序
    seen=set()
    for name,label,nominal,new_val,fuel,sens in sorted(results,key=lambda x:abs(x[5]),reverse=True):
        if name in seen: continue
        seen.add(name)
        print(f"  {name:12s} {nominal:10.1f} {sens:+.4f}  (Δfuel={fuel-base_fuel:+.2f} kg)")


def eval_sensitivity(name,new_val,r0,v0):
    """临时修改参数并求解"""
    global alpha,rho1,rho2,dt,gv,T_min,T2,N_val

    # 复制全局变量
    _m0=m0; _Isp=Isp; _T_max=T_max; _T_frac=T_frac; _T2_frac=T2_frac
    _nT=nT; _phi=phi; _theta=theta_gs; _t_f=t_f; _g_m=g_m; _N=N

    if name=='m0': _m0=new_val
    elif name=='Isp': _Isp=new_val
    elif name=='T_max': _T_max=new_val
    elif name=='T_frac': _T_frac=new_val
    elif name=='T2_frac': _T2_frac=new_val
    elif name=='nT': _nT=int(new_val)
    elif name=='phi_deg': _phi=new_val*np.pi/180
    elif name=='theta_deg': _theta=new_val*np.pi/180
    elif name=='t_f': _t_f=new_val
    elif name=='g_mars': _g_m=new_val
    elif name=='N': _N=int(new_val)
    else: return None

    _alpha=1/(_Isp*g_e*np.cos(_phi))
    _T_min=_T_frac*_T_max; _T2=_T2_frac*_T_max
    _rho1=_nT*_T_min*np.cos(_phi); _rho2=_nT*_T2*np.cos(_phi)
    _dt=_t_f/_N
    _gv=np.array([_g_m,0.,0.])

    def z_ref(k): return np.log(_m0-_alpha*_rho2*k*_dt)
    def mu1(k): return _rho1*np.exp(-z_ref(k))
    def mu2(k): return _rho2*np.exp(-z_ref(k))

    r=[cp.Variable(3) for _ in range(_N+1)]; v=[cp.Variable(3) for _ in range(_N+1)]
    z=[cp.Variable(1) for _ in range(_N+1)]; u=[cp.Variable(3) for _ in range(_N+1)]
    s=[cp.Variable(1) for _ in range(_N+1)]
    cst=[r[0]==r0,v[0]==v0,z[0]==np.log(_m0),r[_N]==0,v[_N]==0]
    for k in range(_N):
        cst+=[r[k+1]==r[k]+v[k]*_dt+0.5*u[k]*_dt*_dt-0.5*_gv*_dt*_dt]
        cst+=[v[k+1]==v[k]+u[k]*_dt-_gv*_dt]
        cst+=[z[k+1]==z[k]-_alpha*s[k]*_dt]
    for k in range(_N+1):
        zk=z[k][0]; sk=s[k][0]
        cst+=[mu1(k)*(zk-z_ref(k)-1)+sk>=0]
        cst+=[mu2(k)*(zk-z_ref(k)-1)+sk<=0]
        cst+=[zk>=np.log(_m0-_alpha*_rho2*k*_dt)]
        cst+=[zk<=np.log(_m0-_alpha*_rho1*k*_dt)]
        cst+=[cp.SOC(r[k][0]*np.tan(_theta),cp.vstack([r[k][1],r[k][2]]))]
        cst+=[cp.SOC(sk,u[k])]
    prob=cp.Problem(cp.Minimize(sum(s[k] for k in range(_N+1))),cst)
    try:
        prob.solve(solver=cp.ECOS,verbose=False)
        if prob.status=='optimal':
            return _m0-np.exp(float(z[_N].value[0]))
    except:
        pass
    return None


# ======================== Main ===============================================

if __name__=='__main__':
    is_full = '--full' in sys.argv
    is_sens = '--sens' in sys.argv

    if not is_sens:
        monte_carlo(1000 if is_full else 100)

    if is_sens or not is_sens:
        sensitivity()

    print(f"\n{'='*60}")
    print(f"  完成. 用法: python3 mars_robustness.py [--full] [--sens]")
    print(f"{'='*60}")
