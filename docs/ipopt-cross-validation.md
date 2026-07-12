# IPOPT NLP 交叉验证 SOCP 方法论

> 用非线性规划 (NLP) 求解器独立验证 SOCP 结果，排除凸化线性化引入的误差。

---

## 一、为什么需要交叉验证

SOCP 求解器（ECOS）使用了两个凸化技巧：

1. **质量对数线性化**：`μ(z - z₀ - 1) + σ` 是原非线性质量约束的一阶泰勒近似
2. **推力松弛**：`||u|| ≤ σ` 替代了非凸的 `T_min ≤ ||T|| ≤ T_max`

这些凸化是"无损"的（Lossless Convexification），理论上 SOCP 解就是原问题的最优解。但在调试阶段，我们需要一个**不使用这些凸化技巧**的独立求解器来验证。

IPOPT 作为通用 NLP 求解器，可以直接处理：
- 非线性质量约束（不经过线性化）
- `||u|| ≤ σ` 作为非线性约束（不经过 SOC 锥）

---

## 二、SOC 锥的光滑等价形式

IPOPT 无法处理原生 SOC 锥 `||x|| ≤ t`（在边界处不可微），需要用光滑等价形式。

### 2.1 平方形式（推荐）

```
||x|| ≤ t  ⇔  t² - x₁² - ... - x_n² ≥ 0  且  t ≥ 0
```

在 IPOPT 中实现为两个不等式约束 `g(x) ≥ 0`：

```python
# 下滑角锥: ||[ry, rz]|| ≤ rx·tan(θ)
ineq += [(rx*tanθ)² - ry² - rz²]   # ≥ 0: 平方形式
ineq += [rx*tanθ]                    # ≥ 0: 确保非负

# 推力松弛锥: ||[ux, uy, uz]|| ≤ σ
ineq += [σ² - ux² - uy² - uz²]     # ≥ 0: 平方形式
ineq += [σ]                          # ≥ 0: 确保非负
```

### 2.2 CasADi 实现

```python
import casadi as ca

# SOC 下滑角
ineq.append(rx**2 * ca.tan(theta)**2 - ry**2 - rz**2)
ineq.append(rx * ca.tan(theta))

# SOC 推力
ineq.append(sigma**2 - ux**2 - uy**2 - uz**2)
ineq.append(sigma)
```

然后将这些加入 `g_all` 向量，`lbg = [0] * len(ineq)`, `ubg = [inf] * len(ineq)`。

---

## 三、常见错误

### 错误：把 SOC 锥拆成标量约束（❌）

```python
# 错误！这不是 SOC 锥约束
ineq += [rx * tanθ, ry, rz]        # 等价于 rx≥0, ry≥0, rz≥0
ineq += [sigma, ux, uy, uz]        # 等价于 sigma≥0, ux≥0, ...
```

这是 `mars_solve.py` 旧版的错误。把 SOC 锥的每个分量单独作为 `≥0` 约束，丢失了"范数≤标量"的结构，结果偏差 23.5%（306.6 vs 400.7 kg）。

**为什么错了？** SOC 锥 `||x|| ≤ t` 要求的不只是各分量非负，而是 **平方范数不超过标量的平方**。

---

## 四、IPOPT vs ECOS 对比

| 特性 | ECOS (SOCP) | IPOPT (NLP) |
|------|-------------|-------------|
| 锥约束 | 原生 SOC | 光滑等价形式 |
| 质量约束 | 线性化 | 真实非线性 |
| 凸性保证 | 全局最优 | 局部最优（但问题凸，等价） |
| 速度 | ~0.1 ms/次 | ~50 ms/次 |
| 适用场景 | 嵌入式实时 | 离线验证 |
| 精度 | 高（内点法） | 稍低（SQP） |

---

## 五、调试工作流

当多个求解器结果不一致时：

```
1. 先用 IPOPT NLP 求解 → 作为独立「真值」参考
2. 如果 ECOS ≠ IPOPT：
   a. 检查 SOC 锥符号（见 docs/ecos-soc-convention.md）
   b. 检查质量线性化系数 μ₁, μ₂
   c. 导出 CCS 矩阵逐元素对比
3. 如果 ECOS ≈ IPOPT，但内部版本间有差异：
   a. 检查参数一致性（T_2 vs T_max 等）
   b. 检查 ECOS 版本差异
```

---

## 六、本项目验证结果（2026-07-12）

| 求解器 | 方法 | 燃料 | 偏差 |
|--------|------|------|------|
| ECOS (C手写) | SOCP | 400.7 kg | 基准 |
| ECOS (C自动) | SOCP | 400.7 kg | 0% |
| ECOS (CVXPY) | SOCP | 400.7 kg | 0% |
| IPOPT (CasADi) | NLP 光滑等价 | 400.7 kg | 0% |

四者完全一致，确认模型和实现正确。

---

## 七、相关文档

- `docs/ecos-soc-convention.md` — ECOS SOC 符号约定
- `docs/debugging-methodology.md` — SOCP 调试通用方法
- `AGENTS.md` — 项目手册
