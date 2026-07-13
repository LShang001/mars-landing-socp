#!/usr/bin/env python3
"""
mars_params.py 单元测试 — 验证参数一致性
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from mars_params import *

def test_derived_params():
    """验证派生参数计算正确"""
    assert abs(phi - 27.0 * np.pi / 180.0) < 1e-10, "phi计算错误"
    assert abs(alpha - 1.0 / (I_sp * g_earth * np.cos(phi))) < 1e-10, "alpha计算错误"
    assert rho1 == n_T * T_min * np.cos(phi), "rho1计算错误"
    assert rho2 == n_T * T2 * np.cos(phi), "rho2计算错误"
    assert dt == t_f / N, "dt计算错误"
    assert abs(g_mars - 3.7114) < 1e-6, "g_mars错误"

def test_initial_conditions():
    """验证初始状态符合物理约束"""
    assert r0[0] == 1500.0, "初始高度应为1500m"
    assert r0[2] == 2000.0, "初始Z位置应为2000m"
    assert v0[0] == -75.0, "初始下降速度应为-75m/s"
    assert v0[2] == 100.0, "初始Z速度应为100m/s"
    assert m0 > m_dry, f"初重{m0}应大于干重{m_dry}"

def test_terminal_conditions():
    """验证终端条件"""
    assert np.all(rf == 0), "终端位置应为0"
    assert np.all(vf == 0), "终端速度应为0(软着陆)"

def test_thrust_params():
    """验证推力参数"""
    assert T_min < T2 < T_max, f"推力: T_min={T_min} < T2={T2} < T_max={T_max}"
    assert T_frac == 0.3, "最小推力比例应为30%"
    assert T2_frac == 0.8, "推力上界应为80%(留20%姿控余量)"

def test_mass_consistency():
    """验证质量参数"""
    m_fuel = m0 - m_dry
    assert m_fuel > 0, "燃料质量应为正"
    assert m_fuel <= GOLD_STANDARD, f"干重法燃料{m_fuel}应≤优化燃料{GOLD_STANDARD}"


def test_golden_standard():
    """黄金基准值回归测试"""
    assert abs(GOLD_STANDARD - 400.7) < 0.01, \
        f"GOLD_STANDARD={GOLD_STANDARD} 偏离 400.7"

def test_time_params():
    """时间参数"""
    assert t_f == 81.0, "着陆时间应为81s"
    assert N == 30, "离散点应为30"
    assert dt == t_f / N, "dt=t_f/N"


if __name__ == '__main__':
    # Simple test runner (no pytest dependency required)
    import traceback
    tests = [f for name, f in sorted(globals().items()) if name.startswith('test_')]
    passed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  ✅ {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test_fn.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test_fn.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{passed}/{len(tests)} 通过")
    sys.exit(0 if passed == len(tests) else 1)
