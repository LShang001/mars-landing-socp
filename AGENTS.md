# AGENTS.md — 火星着陆 SOCP 轨迹优化项目手册

> 本文件面向AI协作者和人类开发者。新会话启动时自动加载, 包含项目约定、陷阱和基准。

---

## 一、项目概述

火星动力下降轨迹优化, 基于 ECOS 二阶锥规划 (SOCP) 求解器。
将非线性最优控制问题通过直接转录法离散化为 N=30 步 SOCP, 手写稀疏矩阵喂给 ECOS。

**仓库**: https://github.com/LShang001/mars-landing-socp  
**作者**: [LShang001](https://github.com/LShang001) — 航天制导与控制工程师  
**硬件**: Intel N150 (LattePanda Iota), 8GB, 64GB eMMC  
**系统**: Ubuntu 24.04, GCC 13.3, kernel 6.17 OEM  

---

## 二、目标与约束

**目标**: 最小化燃料消耗 min Σσ_k·dt  
**物理参数** (见 `MarsLanding/MarsLanding.h`):

| 参数 | 值 | 说明 |
|------|-----|------|
| g | 3.7114 m/s² | 火星重力 |
| Isp | 225 s | 比冲 |
| T_min / T_max | 930 / 3100 N | 单台推力边界 |
| T_2 | 2480 N | 推力上界 (80%额定, 留20%姿控余量) |
| n_T | 6 | 发动机数量 |
| φ | 27° | 安装倾角 |
| θ | 86° | 下滑角 |
| m0 | 1905 kg | 初始质量 |
| m_dry | 1505 kg | 干重 |
| tf | 81 s | 着陆时间 |
| N | 30 | 离散点数 |
| r0 | [1500, 0, 2000] m | 初始位置 |
| v0 | [-75, 0, 100] m/s | 初始速度 |
| rf / vf | [0, 0, 0] | 终端位置/速度 |

**决策变量**: 每步 11 维 (rx, ry, rz, vx, vy, vz, z=ln m, ux, uy, uz, σ), 共 341 维。

**约束**:
- 线性: 质量值不等式 (上下界 via mu1/mu2 线性化), 质量上下界
- 二阶锥: 下滑角 SOC (||[ry,rz]|| ≤ rx·tanθ), 推力松弛 SOC (||[ux,uy,uz]|| ≤ σ)

---

## 三、目录结构

```
mars-landing-socp/
├── CMakeLists.txt              # 3 个目标: ecos_avx, ecos_scalar, ecos_auto
├── MarsLanding/
│   ├── MarsLanding.h           # 问题定义 (维度宏)
│   ├── MarsLanding.c           # 主程序 — 手写 CRS→CCS 矩阵构造 + ECOS
│   ├── CRM2CCM.c               # 稀疏矩阵 CRS→CCS 格式转换
│   ├── MarsLandingAuto.c       # 自动建模版 (CasADi 生成 CCS)
│   ├── MarsLandingAutoData.h   # CasADi 生成的 CCS 矩阵数据 (机器生成)
│   ├── mars_solve.py           # Python 多求解器交叉验证 (ECOS + IPOPT + acados)
│   ├── mars_model.py           # CasADi 建模 + 矩阵验证
│   ├── mars_codegen.py         # CasADi → C 头文件代码生成
│   └── mars_acados.py          # acados SQP 求解器 (实验性)
├── docs/                       # 经验文档 (可复用参考)
│   ├── ecos-soc-convention.md  # ECOS SOC 锥符号约定
│   ├── ipopt-cross-validation.md  # IPOPT 交叉验证方法
│   └── debugging-methodology.md   # SOCP 调试方法论
├── ecos/                       # ECOS v2.0.10 官方满血版 (含指数锥)
│   ├── src/                    # 13 个 .c 文件
│   ├── include/                # 14 个 .h 文件
│   └── external/               # AMD (SuiteSparse) + LDL
└── README.md                   # 项目文档 (中文)
```

---

## 四、编译与运行

```bash
git clone git@github.com:LShang001/mars-landing-socp.git
cd mars-landing-socp
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)

# 三版对比
./build/bin/ecos_avx        # C 手写版 (AVX优化)
./build/bin/ecos_scalar     # C 手写版 (标量)
./build/bin/ecos_auto       # C 自动版 (CasADi 生成矩阵)

# Python 交叉验证
cd MarsLanding
python3 mars_solve.py        # CVXPY+ECOS 和 CasADi+IPOPT
python3 mars_model.py        # 模型验证 (矩阵非零元对比)
python3 mars_codegen.py      # 重新生成 MarsLandingAutoData.h

# 修改物理参数后重生成:
python3 mars_codegen.py      # 更新 C 头文件
cd ../build && make -j4       # 重新编译
```

**Python 依赖**: `pip install casadi cvxpy ecos numpy scipy`

---

## 五、物理约定与坐标系

**坐标系统**: x 轴向上 (远离火星表面), yz 水平。  
**重力**: g = +3.7114 m/s², 方向为 +x (向上)。但在动力学中重力提供向下的加速度:
  - 位置: `rx(k+1) = rx(k) + vx(k)·dt + 0.5·ux(k)·dt² - 0.5·g·dt²`
  - 速度: `vx(k+1) = vx(k) + ux(k)·dt - g·dt`

**ECOS 符号约定** (关键!):
  - 不等式: `h - Gx ≥ 0` (线性), `h - Gx ∈ K_q` (锥)
  - 等式: `Ax = b`
  - CasADi eq 形式: `eq = 0`, 则 `A = jacobian(eq, x)`, `b = -eq(0)`
  - **如果 eq 中有 `+g·dt` 项, 则 b 中有 `-g·dt`, 显式形式为 `-g·dt`**

---

## 六、已知陷阱 (修改代码前必读)

1. **T_2 = 0.8 * T_max 不能丢**: 推力上界是 80% 额定 (留姿控余量), 不是 T_max。
2. **重力符号极易写反**: 在手写版约定中, 所有重力项都是负贡献。CasADi eq 中为 `+g`, 但显式动力学中变为 `-g`。详见第五节物理约定。
3. **ECOS SOC 锥符号必须为负**: 锥约束 `h-Gx ∈ K_q` 中, G 矩阵的行必须用负系数, 使 `h-Gx = [rx·tanθ, ry, rz]` 而非取反。正系数会导致 rx ≤ 0 (违反物理)。参见 mars_model.py 和 mars_codegen.py 中的 `-rx, -ry, -rz` 等。
4. **ECOS G 矩阵行序**: 前 `l=124` 行必须全是线性约束, 后 217 行为锥约束, 不能交错。
5. **CRS_PUSH 宏**: 如果修改宏实现, 必须确保 `row_nnz` 正确递增。
6. **ECOS 2.0.10 是官方满血版**: 我们的 ecos/ 目录来自官方 v2.0.10 (embotech/ecos) + 额外文件 expcone.c/wright_omega.c。ECOS 实例的 PROFILING=2 和 CTRLC=0 通过 CMake 定义。
7. **CasADi DM 赋值**: `float(DM[i])` 或 `.nz` 访问, 不能 `list()` 迭代。
8. **Python ecos.solve 签名**: `ecos.solve(c, G, h, dims, A=A, b=b)`, 不是 `ecos.solve(c, G, dims, A, b, h)`。
9. **CasADi b/h 提取公式**: `b = -eq(0)`, `h = -ineq(0)`，不是 `-A@x+eq`。旧版 mars_model.py 曾用后一种公式导致 b/h 符号错误。验证方法：b[0] 应等于 r₀[0]=1500（正数），b[13]=½g·dt²=13.528（正数）。
10. **IPOPT 不能直接用 SOC 锥**: IPOPT 不支持 `||x|| ≤ t` 形式，必须在 NLP 中写为光滑等价形式 `t² - x₁² - ... ≥ 0` 且 `t ≥ 0`。把 SOC 拆成标量 `rx≥0, ry≥0, rz≥0` 是错误做法——丢失了范数约束，结果偏差可达 23%。
11. **acados 惩罚法优于硬约束**: 硬约束 `con_h_expr` 在 u≈0 处 Hessian 病态导致 QP 崩溃。将 SOC 约束转为 softplus 惩罚项加入 LS 代价, 配合多轮 continuation (w=10→1e5), 可精确匹配 ECOS 400.7 kg。详见 mars_acados.py。
12. **单精度 (float) 不可用于此问题**: Clarabel f32 虽然快 50x (0.12 ms vs 6 ms), 但燃料误差 375%。根因: 问题动态范围大 (位置 1500, exp(-z)~0.0005), float 条件数不足。嵌入式部署必须用 double。详见 benchmarks/clarabel_float_bench.c。

### 陷阱 13：单精度(float)对该问题产生 375% 燃料误差
Clarabel f32 基准实测燃料 1880+ kg，误差 375%。根因：动态范围 10^6.6（位置 ~2000 m vs exp(-z) ~0.0005），float 仅 7 位有效数字，不足以在 KKT 条件数 10^8 下可靠求解。ECOS glblopts.h:54 声明 pfloat 必须为 double。建议在 CMakeLists.txt 或 main 入口加静态断言。

### 陷阱 14：ln(m) 质量对数变换引入约 1500 倍误差放大
由于 dm/dz = m ≈ 1505-1905 kg，z_N 的 1e-7 误差转换为燃料质量时放大 ~1500 倍 → 1.5e-4 kg。燃料 400.7 kg 对应 Δz = 0.236，z 误差 0.001 即导致约 1.5 kg 燃料偏差。调试线索：交叉验证中发现 ~0.1 kg 量级偏差时，回溯 z_N 误差仅约 7e-5。

### 陷阱 15：C 手写版与 CasADi 代码生成版的 A 矩阵符号约定相反
C 版写为 A*x=b（如 rx_k + dt*vx_k + ... = +½g·dt²），CasADi 版提取 A=jacobian(eq,x) b=-eq(0)，得到符号相反的矩阵（如 -rx_k - dt*vx_k - ... = -½g·dt²）。两者物理等价但矩阵数值符号相反。进行逐元素对比时注意此约定差异。

### 陷阱 16：mars_model.py 与 mars_codegen.py 的线性约束行序不同
mars_model.py 用与 C 手写版一致的分组行序（先全部质量值不等式 62 行，再全部质量上下界 62 行）。mars_codegen.py 用按 k 交错的行序（每个 k 步内交替排列）。两种行序数学等价但 G 矩阵行号完全不同。混用两份文件输出会引入隐蔽 Bug。建议统一为分组行序。

### 陷阱 17：AVX/FMA 编译选项对稀疏 LDL 分解无效
ECOS_USE_AVX=1 在源码中无任何 _mm256_* intrinsic。实测标量版比 AVX 版快 2.4%。根因：稀疏 LDL 分解是内存带宽瓶颈（CCS 格式 irregular gather/scatter），SIMD 无法加速。不应再尝试对稀疏求解器加 SIMD 编译选项——如需加速应改写算法而非加编译器 flag。

### 陷阱 18：acados lbu 不能限制 u 分量符号
acados 的 lbu=[0,0,0,0] 强制 ux,uy,uz ≥ 0，但原始 ECOS 问题中 u 只有锥约束 ‖u‖ ≤ σ 无符号限制。uz 必须为负才能让 vz 从 +100 减速到 0。限制 uz≥0 导致问题不可行。只应限制 sigma ≥ 0。

### 陷阱 19：acados continuation warm-start 必须在循环内部更新 x_guess
x_guess/u_guess 的更新必须在 for w in weights 循环内部执行，否则三个权重都从相同初始猜测起步。

---

## 七、acados 安装 (实验性)

acados 是 C 编写的嵌入式最优控制求解器，使用 SQP + HPIPM。安装步骤：

```bash
# 1. 克隆 & 编译
sudo git clone --depth 1 --recurse-submodules \
    https://github.com/acados/acados.git /opt/acados
sudo chown -R $USER:$USER /opt/acados
cd /opt/acados && mkdir build && cd build
cmake .. -DACADOS_WITH_QPOASES=OFF -DACADOS_WITH_OSQP=OFF
make -j$(nproc) && make install

# 2. Tera 渲染器 (模板代码生成)
curl -sL --socks5 127.0.0.1:10808 \
    -o /opt/acados/bin/t_renderer \
    https://github.com/acados/tera_renderer/releases/download/v0.2.0/t_renderer-v0.2.0-linux-amd64
chmod +x /opt/acados/bin/t_renderer

# 3. Python 接口
pip3 install --break-system-packages -e /opt/acados/interfaces/acados_template

# 4. 环境变量 (追加到 ~/.bashrc)
export ACADOS_SOURCE_DIR=/opt/acados
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/acados/lib
```

**验证**: `python3 -c "from acados_template import AcadosOcp; print('OK')"`
**运行**: `cd MarsLanding && python3 mars_acados.py`

---

## 八、经验文档索引

项目 `docs/` 目录包含可复用的深度参考文档，修改代码前建议查阅：

| 文档 | 内容 | 适用场景 |
|------|------|----------|
| [docs/ecos-soc-convention.md](docs/ecos-soc-convention.md) | ECOS SOC 锥符号约定、h-Gx ∈ K 推导、CasADi 提取公式 | 新增/修改 SOC 约束时 |
| [docs/ipopt-cross-validation.md](docs/ipopt-cross-validation.md) | IPOPT 光滑等价形式、与 SOCP 对比、交叉验证方法 | 求解器结果不一致时 |
| [docs/debugging-methodology.md](docs/debugging-methodology.md) | L1-L3 分级排查流程、关键行快速验证、典型案例 | 任何调试场景 |

---

## 九、验证基准

**黄金标准**: 所有求解器必须输出 `400.7 kg` 燃料消耗。

| 求解器 | 方法 | 预期 |
|--------|------|------|
| C 手写 AVX/SCL | ECOS SOCP | 400.7 kg |
| C 自动 | ECOS SOCP | 400.7 kg |
| Python CVXPY+ECOS | SOCP | 400.7 kg |
| Python CVXPY+Clarabel | SOCP | 400.7 kg |
| Python IPOPT | NLP (光滑等价) | 400.7 kg |
| Python acados | NLP SQP (惩罚法) | 400.7 kg |

**验证命令**:
```bash
cd build && make -j4 && \
  (./bin/ecos_avx | grep 燃料) && \
  (./bin/ecos_auto | grep 燃料) && \
  (cd ../MarsLanding && python3 -c "from mars_solve import solve_cvxpy_ecos;f,_=solve_cvxpy_ecos();print(f'CVXPY: {f:.1f} kg')")
```

---

## 十、多求解器交叉验证

| 版本 | 求解器 | 建模方式 | 燃料 | 偏差 |
|------|--------|----------|------|------|
| C 手写 | ECOS 2.0.10 | 手写 CRS→CCS 矩阵 | 400.7 kg | 基准 |
| C 自动 | ECOS 2.0.10 | CasADi 生成 CCS | 400.7 kg | 0% |
| Py CVXPY+ECOS | ECOS 2.0.14 | CVXPY SOCP 建模 | 400.7 kg | 0% |
| Py CVXPY+Clarabel | Clarabel 0.11 | CVXPY SOCP 建模 | 400.7 kg | 0% |
| Py IPOPT | IPOPT 3.x | CasADi NLP (SOC光滑等价) | 400.7 kg | 0% |
| Py acados | acados SQP | CasADi NLP (惩罚法) | 400.7 kg | 0% |

> Clarabel (2023, Rust 实现) 比 ECOS 快 34% (177 vs 268 ms in CVXPY), 数值更稳定。嵌入式 C 库可在 clarabel.dev 获取。
> IPOPT 使用光滑等价形式 `(rx·tanθ)² - ry² - rz² ≥ 0` 和 `σ² - ‖u‖² ≥ 0` 替代原 SOC 锥约束。
> acados 使用惩罚法 (continuation: w=10→1e3→1e5), softplus 光滑化 SOC 约束加入 LS 代价, GAUSS_NEWTON SQP 求解。

---

## 十一、代码风格

- 中文注释 (物理/数学以中文为主, 符号保留英文)
- 变量命名: 状态用 `r_x, v_x, z`, 控制用 `u_x, σ` (sigma)
- C 代码: `snake_case`, 宏用 `UPPER_CASE`, 索引用 `k` (时间步), `idx_*` (非零元)
- Python: 类型标注不强制, 但关键函数有 docstring
- 提交信息: 中文描述 + 类型前缀 (feat/fix/doc/refactor)

---

## 十二、Git 协同

- 仓库: `git@github.com:LShang001/mars-landing-socp.git`
- 分支: 直接推 master (无 PR 流程, 无分支保护)
- 提交前: `make -j4 && ./bin/ecos_avx | grep 燃料` 确认 400.7 kg
- `.gitignore` 排除: `build/`, `*.o`, `__pycache__/`, `*.pyc`

---

## 十三、相关资源

- ECOS 官方: https://github.com/embotech/ecos
- CasADi: https://web.casadi.org/
- CVXPY: https://www.cvxpy.org/
- 记忆中的相关 skill: `code-review-discipline`, `mars-landing-lessons`, `github-ssh-push`
