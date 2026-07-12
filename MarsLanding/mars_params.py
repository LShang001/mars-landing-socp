"""
=============================================================================
 mars_params.py — 火星着陆物理参数 (唯一来源)
=============================================================================

项目中所有 Python 和 C 代码的参数定义必须与此文件一致。
修改物理参数时只改这里，然后运行:
  python3 mars_codegen.py       # 重新生成 C 头文件
  cd ../build && make -j4        # 重新编译 C 代码
  python3 mars_solve.py          # 验证全部 400.7 kg

作者: LShang + Claude
日期: 2026-07-13
=============================================================================
"""

import numpy as np

# ---- 物理常数 ----
g_mars  = 3.7114        # 火星重力加速度 [m/s²]
g_earth = 9.807          # 地球重力加速度 [m/s²] (用于 Isp 换算)

# ---- 航天器参数 ----
m0      = 1905.0         # 初始质量 [kg]
m_dry   = 1505.0         # 干重 [kg]
I_sp    = 225.0          # 发动机比冲 [s]
T_max   = 3.1e3          # 单台发动机最大推力 [N]
T_frac  = 0.3            # 最小推力比例 (T_min = T_frac * T_max)
T2_frac = 0.8            # 推力上界比例 (留 20% 姿控余量)
n_T     = 6              # 发动机数量
phi_deg = 27.0           # 发动机安装倾角 [°]
theta_deg = 86.0         # 下滑角 [°] (= 90° - 4°, 近乎垂直)

# ---- 任务参数 ----
t_f     = 81.0           # 着陆时间 [s]
N       = 30             # 离散点数

# ---- 初始/终端条件 ----
r0 = np.array([1500.0, 0.0, 2000.0])   # 初始位置 [m]
v0 = np.array([-75.0,  0.0, 100.0])    # 初始速度 [m/s]
rf = np.array([0.0,    0.0, 0.0])      # 终端位置 [m] (着陆点)
vf = np.array([0.0,    0.0, 0.0])      # 终端速度 [m/s] (软着陆)

# ---- 派生参数 (自动计算, 不要手动修改) ----
phi      = phi_deg * np.pi / 180.0
theta    = theta_deg * np.pi / 180.0
T_min    = T_frac * T_max
T2       = T2_frac * T_max
alpha    = 1.0 / (I_sp * g_earth * np.cos(phi))
rho1     = n_T * T_min * np.cos(phi)    # 最小有效推力 [N]
rho2     = n_T * T2   * np.cos(phi)    # 最大有效推力 [N] (80% 额定)
dt       = t_f / N
gv       = np.array([g_mars, 0.0, 0.0])  # +x 向上, 重力向下(-x)

# ---- 参考轨迹 (时变参数) ----
def z_ref(k: int) -> float:
    """质量对数参考轨迹 z₀(k)"""
    return np.log(m0 - alpha * rho2 * k * dt)

def mu1(k: int) -> float:
    """线性化系数 μ₁(k) — 下界"""
    return rho1 * np.exp(-z_ref(k))

def mu2(k: int) -> float:
    """线性化系数 μ₂(k) — 上界"""
    return rho2 * np.exp(-z_ref(k))

# ---- 基准解 ----
GOLD_STANDARD = 400.7  # 所有求解器必须输出此值 [kg]
