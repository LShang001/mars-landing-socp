# SOCP 轨迹优化调试方法论

> 当 SOCP 求解结果异常时，从粗到细的系统排查流程。适用于火星着陆和 VTVL 轨迹规划项目。

---

## 一、问题分类

SOCP 轨迹优化的 bug 通常分为三层：

| 层级 | 典型症状 | 常见原因 |
|------|----------|----------|
| L1: 求解器失败 | ECOS_setup 返回 NULL / exitflag != OPTIMAL | 维度不匹配、约束矛盾 |
| L2: 结果偏差大 | 燃料偏差 > 1% | 重力符号、参数遗漏、锥符号 |
| L3: 结果偏差小 | 燃料偏差 < 1% 但版本间不一致 | 数值敏感性、ECOS 版本差异 |

---

## 二、L1 排查：求解器失败

### 2.1 维度检查

```c
// 打印关键维度
printf("n=%d m=%d p=%d l=%d ncones=%d\n",
       N_VAR, M_G, P_EQ, L_G, NCONES);

// 验证 G 矩阵行数
assert(M_G == L_G + (ncones_for_glide * 3) + (ncones_for_thrust * 4));
```

### 2.2 矩阵非零元检查

```c
assert(nnzA == nnz_bound + nnz_dyn * N);  // 733
assert(nnzG == (nnz_Tnorm + nnz_mass + nnz_Trelax + nnz_slope) * (N+1));  // 403
```

### 2.3 约束排序检查

ECOS 要求 G 矩阵前 `l` 行全为线性约束，后 `m-l` 行为锥约束。**不能交错。**

常见错误：按时间步 k 交错排列线性/SOC 约束（`mars_model.py` 旧版曾犯），导致 ECOS 把 SOC 行当线性处理。

---

## 三、L2 排查：结果偏差大

### 3.1 黄金基准

火星着陆项目的黄金基准：**400.7 kg** 燃料消耗。

所有求解器输出必须以这个值为准。偏差 > 1 kg 就需要排查。

### 3.2 参数完整性检查

逐项对比物理参数初始化代码：

```
□ g = 3.7114（不是 9.807）
□ T_2 = 0.8 * T_max（不是 T_max） ← 最容易遗漏
□ n_T = 6（发动机数量）
□ φ = 27°（安装倾角）
□ θ = 86° = 90° - 4°（下滑角）
□ m₀ = 1905 kg
□ t_f = 81 s
```

### 3.3 重力符号检查

物理约定：+x 向上，重力向下(-g)。

验证方法：检查 `b[13]`（rx 动力学常数项）。
- 正确：`b[13] = +½g·dt² = +13.528`
- 如果为负：重力符号反了

### 3.4 SOC 锥符号检查

验证方法：检查 `h[124]` 和 `h[217]`。
- 正确：都为 0
- 如果非零：SOC 行序或符号有问题

详见 `docs/ecos-soc-convention.md`。

---

## 四、L3 排查：稀疏矩阵逐元素对比

### 4.1 导出 C 代码的 CCS 矩阵

在 `MarsLanding.c` 中临时添加 dump 代码：

```c
// 导出 CCS 数组到文件
FILE *f = fopen("/tmp/ccs_dump.txt", "w");
for (int i = 0; i < NNZA; i++) {
    fprintf(f, "A_pr[%d]=%.12f  A_ir[%d]=%d\n", i, CCApr[i], i, CCAir[i]);
}
fclose(f);
```

### 4.2 Python 端加载 CasADi 矩阵

```python
import casadi as ca
import numpy as np

# 生成 CasADi 矩阵
A_casadi = ca.Function('A', [x], [ca.jacobian(eq, x)])(ca.DM.zeros(N_VAR))
G_casadi = ca.Function('G', [x], [ca.jacobian(ineq, x)])(ca.DM.zeros(N_VAR))

# 转为稠密逐元素对比
A_dense = ca.DM(A_casadi)
for i in range(A_dense.size1()):
    for j in range(A_dense.size2()):
        if abs(float(A_dense[i,j])) > 1e-12:
            # 与 C 代码的 dump 对比
            pass
```

### 4.3 关键行的快速验证

不需要对比所有 733+403=1136 个非零元。验证以下关键行即可覆盖大部分 bug：

| 矩阵 | 行 | 对应约束 | 关键检查 |
|------|-----|----------|----------|
| A | 0 | rx₀ = 1500 | b=1500 |
| A | 13 | rx₁ 动力学 | b=13.528, 4 个非零元 |
| A | 16 | vx₁ 动力学 | b=10.021, 3 个非零元 |
| G | 0 | 质量下界 | 2 个非零元, h 为负 |
| G | 124 | 下滑角锥 k=0 | 3 个非零元, h=0 |
| G | 217 | 推力锥 k=0 | 4 个非零元, h=0 |

---

## 五、四求解器交叉验证矩阵

| 求解器 | 建模 | 矩阵来源 | 用途 |
|--------|------|----------|------|
| C 手写 (ECOS) | 手写 CRS→CCS | 人工构造 | 嵌入式部署基准 |
| C 自动 (ECOS) | CasADi → CCS | 自动生成 | 验证手写矩阵 |
| Python CVXPY (ECOS) | CVXPY SOCP | 自动构造 | 独立实现验证 |
| Python IPOPT | CasADi NLP | 自动构造 | 排除线性化误差 |

**原则**：至少两个独立实现的结果一致才能确认正确。

---

## 六、典型案例

### 案例 1：重力符号反了（2026-07-12）

- 表现：CasADi+IPOPT 306.6 kg vs ECOS 400.7 kg（-23.5%）
- 根因：`mars_solve.py` 中 SOC 锥约束写成了标量 ≥0（错误），而非光滑等价形式
- 修复：改用 `(rx·tanθ)² - ry² - rz² ≥ 0` 和 `σ² - ‖u‖² ≥ 0`
- 详见：`docs/ipopt-cross-validation.md`

### 案例 2：SOC 锥符号错误（2026-07-12）

- 表现：`mars_model.py` 声称 nnz 匹配，但 h[124] ≠ 0
- 根因 1：SOC 锥用正系数（应为负）
- 根因 2：约束按 k 交错排列（应线性先行）
- 根因 3：b/h 提取公式用了 `-A@x+eq` 而非 `-eq(0)`
- 修复：三处全部修正，验证 b/h 关键行数值
- 详见：`docs/ecos-soc-convention.md`

---

## 七、相关文档

- `AGENTS.md` — 项目手册，完整陷阱列表
- `docs/ecos-soc-convention.md` — ECOS SOC 符号约定
- `docs/ipopt-cross-validation.md` — IPOPT 交叉验证
