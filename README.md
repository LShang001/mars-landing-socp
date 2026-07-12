# ECOS 火星着陆轨迹优化

> Embedded Conic Solver — Mars Landing Trajectory Optimization  
> 针对 Intel Alder Lake-N (N150 / Gracemont) 优化  
> 基于二阶锥规划（SOCP）的火星动力下降轨迹优化

---

## 一、项目概述

本项目使用 ECOS（Embedded Conic Solver）求解器，通过 SOCP（二阶锥规划）方法求解火星着陆动力下降段的最优轨迹。项目提供两个编译目标：AVX 加速版和纯标量版，可根据 CPU 频率/功耗需求选择。

**核心问题：** 给定初始状态（位置、速度、质量）和终端状态（着陆点），在满足推力约束、下滑角约束和燃料约束的前提下，找到最小燃料消耗的推力控制序列。

---

## 二、目录结构

```
ecos-cn-raspberry/
├── CMakeLists.txt              # CMake 构建（4 目标: avx,scalar,auto,clarabel）
├── CLAUDE.md                   # Claude Code 入口（@AGENTS.md 桥接）
├── AGENTS.md                   # 项目手册（13 节, 12 条陷阱, AI 自动加载）
├── ci/
│   └── validate.sh             # 一键验证（7 求解器, bash ci/validate.sh）
├── MarsLanding/
│   ├── mars_params.py          # ★ 物理参数唯一来源
│   ├── mars_solve.py           # 4 求解器交叉验证（ECOS+Clarabel+IPOPT+acados）
│   ├── mars_model.py           # CasADi 建模 + 矩阵数值验证
│   ├── mars_codegen.py         # CasADi → C 头文件代码生成
│   ├── mars_acados.py          # acados SQP 惩罚法求解器
│   ├── mars_robustness.py      # Monte Carlo 鲁棒性 + 灵敏度分析
│   ├── MarsLanding.h           # 问题参数头文件
│   ├── MarsLanding.c           # C 手写版（CRS→CCS + ECOS）
│   ├── MarsLandingAuto.c       # C 自动版（CasADi 生成 CCS）
│   ├── MarsLandingAutoData.h   # CasADi 生成的 CCS 矩阵数据
│   └── CRM2CCM.c               # 稀疏矩阵 CRS → CCS 格式转换
├── benchmarks/
│   ├── clarabel_mars.c         # Clarabel C 嵌入式 benchmark
│   └── clarabel_float_bench.c  # Clarabel double vs float 精度对比
├── docs/                       # 经验文档（可复用参考）
│   ├── ecos-soc-convention.md
│   ├── ipopt-cross-validation.md
│   └── debugging-methodology.md
├── ecos/
│   ├── include/                # ECOS 头文件
│   │   ├── ecos.h              # 主头文件（版本 2.0.10，求解器参数）
│   │   ├── cone.h / kkt.h / spla.h / ...
│   │   └── glblopts.h          # 全局编译选项
│   ├── src/                    # ECOS 核心源码
│   │   ├── ecos.c              # 主求解器（内点法 + Mehrotra 预测-校正）
│   │   ├── cone.c              # 锥投影与屏障函数
│   │   ├── kkt.c               # KKT 系统构造与求解
│   │   ├── preproc.c           # 预处理（矩阵缩放、排序）
│   │   ├── equil.c             # 均衡化
│   │   ├── spla.c / splamm.c   # 稀疏线性代数
│   │   └── timer.c             # 计时
│   └── external/
│       ├── amd/                # AMD 矩阵排序（SuiteSparse）
│       │   ├── include/amd.h
│       │   └── src/amd_*.c     # 13 个源文件（排序、验证、树结构）
│       ├── ldl/                # LDL 分解
│       │   ├── include/ldl.h
│       │   └── src/ldl.c
│       └── SuiteSparse_config/
│           └── SuiteSparse_config.h
└── build/                      # 构建输出
    ├── bin/
    │   ├── ecos_avx            # AVX2+FMA 加速版可执行文件
    │   └── ecos_scalar         # 纯标量版可执行文件
    └── CMakeFiles/             # 编译中间文件
```

---

## 三、数学模型

### 3.1 问题维度

| 参数 | 值 | 含义 |
|------|-----|------|
| N | 30 | 离散点数 |
| NX | 7 | 状态维度：rx, ry, rz, vx, vy, vz, z(=ln m) |
| NU | 4 | 控制维度：ux, uy, uz（推力），s（松弛变量） |
| n | (NX+NU)×(N+1) = 341 | 优化变量总数 |
| p | 7 + 7×N = 217 | 等式约束数（边界 + 动力学） |
| l | (N+1)×4 = 124 | 线性不等式约束数 |
| ncones | (N+1)×2 = 62 | 二阶锥数量 |

### 3.2 动力学模型

采用**双积分器 + 质量消耗**模型：

```
r_{k+1} = r_k + v_k·dt + 0.5·u_k·dt² + 0.5·g·dt²
v_{k+1} = v_k + u_k·dt + g·dt
z_{k+1} = z_k - α·s_k·dt
```

其中：
- `z = ln(m)` 为质量对数（凸化处理）
- `α = 1/(I_sp·g_e·cos φ)` 为燃料消耗系数
- `s_k` 为松弛变量，`||u_k|| ≤ s_k`（推力锥约束）
- `g = [3.7114, 0, 0]` 为火星重力加速度（仅 x 方向）

### 3.3 约束条件

| 约束类型 | 数学形式 | 用途 |
|----------|----------|------|
| **边界约束** | `x_0 = x_init`, `x_N = x_final` | 固定初始终端状态 |
| **推力锥约束**（SOC） | `||[ux,uy,uz]|| ≤ σ_k` (q=4) | 推力大小松弛 |
| **下滑角约束**（SOC） | `||[ry,rz]|| ≤ rx·tan(θ)` (q=3) | 防撞地 (rx=高度) |
| **质量下界** | `z_k ≥ ln(m_0 - α·ρ_2·t_k)` | 干重约束 |
| **质量上界** | `z_k ≤ ln(m_0 - α·ρ_1·t_k)` | 燃料上限 |

### 3.4 目标函数

```
min  Σ s_k     （最小化推力松弛 ≈ 最小化燃料）
```

### 3.5 物理参数

| 参数 | 值 | 含义 |
|------|-----|------|
| g | 3.7114 m/s² | 火星重力加速度 |
| g_e | 9.807 m/s² | 地球重力加速度（用于 I_sp 换算） |
| m_0 | 1905 kg | 初始质量 |
| m_dry | 1505 kg | 干重（含结构） |
| I_sp | 225 s | 发动机比冲 |
| T_min | 0.3·T_max = 930 N | 单推力下限（6台 × 930 = 5580 N） |
| T_max | 3.1 kN | 单台发动机最大推力 |
| n_T | 6 | 发动机数量 |
| φ | 27° | 发动机安装倾角 |
| θ_alt | 86° | 下滑角约束（86° = 几乎垂直） |
| t_f | 81 s | 固定终端时间 |
| **初始状态** | | |
| r_0 | [1500, 0, 2000] m | 初始位置 |
| v_0 | [-75, 0, 100] m/s | 初始速度 |
| **终端状态** | | |
| r_f | [0, 0, 0] m | 着陆点 |
| v_f | [0, 0, 0] m/s | 软着陆 |

---

## 四、算法实现

### 4.1 稀疏矩阵手写构造

程序直接在代码中以 CSC（压缩列存储）格式手工填入矩阵 A 和 G 的每个非零元素。这种方法虽然代码冗长，但避免了 MATLAB/自动代码生成的依赖，适合嵌入式移植。

**A 矩阵（等式约束）：**
- 行 0-6：初始边界条件（7 行）
- 行 7-13：终端边界条件（7 行）
- 行 14-223：动力学约束（210 行 = 7 × 30）

**G 矩阵（不等式约束）：**
- 前 62 行：推力质量不等式
- 后 62 行：质量上下界
- 再 93 行：下滑角 SOC 约束
- 最后 93 行：推力松弛 SOC 约束

### 4.2 CRM → CCM 格式转换

稀疏矩阵先以 CRS（行压缩）格式构造（每个约束按行填入非零元素），然后通过 `CRM2CCM()` 函数转换为 ECOS 所需的 CCS（列压缩）格式。

### 4.3 求解流程

```
1. 初始化物理参数和边界条件
2. 计算时变参数（z_0[k], mu_1[k], mu_2[k]）
3. 构造 CRS 格式稀疏矩阵 A 和 G
4. CRM2CCM: 转换为 CCS 格式
5. ECOS_setup: 初始化求解器
6. 循环 1000 次 ECOS_solve（性能测试）
7. ECOS_cleanup: 释放内存
8. 输出：最优燃料消耗、求解时间
```

---

## 五、编译与运行

### 编译

```bash
cd ~/Projects/ecos-cn-raspberry
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### 运行

```bash
# C 嵌入式 (4 目标)
./build/bin/ecos_avx         # AVX2+FMA 加速版
./build/bin/ecos_scalar      # 纯标量版
./build/bin/ecos_auto        # CasADi 自动生成版
./build/bin/ecos_clarabel    # Clarabel C (Rust, 备选)

# 一键验证
bash ci/validate.sh          # 7 求解器（不含 acados）
bash ci/validate.sh --full   # 含 acados + Monte Carlo
```

### 预期输出

```
total time: xxx.x ms              # 1000 次求解总耗时
average factor time: x.xxx s      # 平均矩阵分解时间
average kktsolve time: x.xxx s    # 平均 KKT 求解时间
average total solve time: x.xxx s # 平均单次求解时间
fuel usage = xxx.x kg             # 最优燃料消耗
```

---

## 六、编译选项

| 目标 | 关键编译选项 | 适用场景 |
|------|-------------|----------|
| `ecos_avx` | `-O3 -march=native -mfma` + `ECOS_USE_AVX=1` | AVX2/FMA 向量化，低频率高 IPC |
| `ecos_scalar` | `-O3 -march=native -mno-avx -mno-avx2 -mno-fma` | 无 SIMD，高频率低功耗 |

通用选项：`-fno-finite-math-only -fno-unsafe-math-optimizations`（保证数值稳定性）

---

## 七、求解器参数（ECOS 2.0.10）

| 参数 | 默认值 | 含义 |
|------|--------|------|
| MAXIT | 100 | 最大迭代次数 |
| FEASTOL | 1e-8 | 原始/对偶不可行容差 |
| ABSTOL | 1e-8 | 对偶间隙绝对容差 |
| RELTOL | 1e-8 | 对偶间隙相对容差 |
| GAMMA | 0.99 | 最终步长缩放因子 |
| NITREF | 9 | 迭代精化步数 |

---

## 八、与 VTVL 项目的关系

两个项目共享同一个 ECOS 求解器核心（AMD + LDL + ECOS 源码），微小区別：

| | 本项目 | VTVL 项目 |
|------|--------|------------|
| ecos.c | 原始版本 | +Ctrl-C 中断支持 |
| preproc.c | 保留 debug FLOPs 打印 | 注释掉 debug |

AMD 排序库和 LDL 分解库完全一致。

上层问题建模完全不同：本项目为火星着陆单次开环优化，VTVL 项目为地球 VTVL 分层实时控制（轨迹规划 + MPC 闭环跟踪）。

---

## 九、文档与经验库

项目包含系统化的开发经验和调试文档，新贡献者和 AI 协作者建议按以下顺序阅读：

1. **[AGENTS.md](AGENTS.md)** — 项目手册（AI 自动加载）。物理约定、已知陷阱（10 条）、验证基准、交叉验证矩阵
2. **[docs/ecos-soc-convention.md](docs/ecos-soc-convention.md)** — ECOS SOC 锥符号约定（`h-Gx ∈ K` 推导、CasADi 提取公式、验证清单）
3. **[docs/ipopt-cross-validation.md](docs/ipopt-cross-validation.md)** — IPOPT NLP 光滑等价形式交叉验证 SOCP 的方法论
4. **[docs/debugging-methodology.md](docs/debugging-methodology.md)** — L1-L3 分级排查流程、关键行快速验证、典型案例

> 所有文档均为项目内 markdown 文件，不依赖任何特定 AI 工具，任何协作者均可阅读。

---

## 十、参考资料

- ECOS: Embedded Conic Solver, ETH Zurich / embotech GmbH
- Acikmese & Ploen (2007): "Convex Programming Approach to Powered Descent Guidance for Mars Landing"
- SuiteSparse AMD: Approximate Minimum Degree ordering
