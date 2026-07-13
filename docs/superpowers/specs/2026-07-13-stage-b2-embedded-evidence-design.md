# Stage B2 嵌入式时间与内存证据设计

## 1. 目的与证据边界

Stage B2 建立可复现、可审计的求解器执行时间与内存证据，并取得至少一种非 x86 目标板的实测数据。它不以 Intel N150 推算嵌入式性能，也不把有限次数测得的最大值称为 WCET。

本阶段保留 Stage A 的 `host_measured` 协议和 7.361 ms 历史记录，但明确后者只有以下含义：Intel N150 项目主机、Release `ecos_avx`、矩阵装配及 `ECOS_setup()` 之后、以 `clock()` 累计 1000 次 `ECOS_solve()` 得到的 CPU 时间均值。该记录没有逐次样本，不能补算分位数、观测最大值或端到端时延。

本设计不得修改、生成或替代 `MarsLanding/MarsLanding.c`。该文件仍是作者原始、独立、人工维护的 CRS→CCS 参考实现。B2 只能通过独立基准驱动、编译插桩或求解器侧可选探针测量它；自动生成模型只能用于数值一致性交叉验证。

## 2. 核心原则

1. **测量范围先于数字**：每个样本必须标明开始与结束事件，禁止把不同循环、不同进程或不同仪器的阶段统计相加后称为端到端。
2. **原始样本是权威证据**：汇总值可重算，不删除离群值；超时、不可行、求解错误和采集错误也保留在分母中。
3. **主机与目标板分协议**：`host_measured` 只允许 x86 主机；目标板使用独立的 `target_measured` manifest 和 recorder，不能靠修改平台标签复用主机证据。
4. **时间与可行性绑定**：每次计时记录同时保存 ECOS 状态、迭代数和解审计结果，避免用快速失败样本改善时延统计。
5. **内存按来源分层**：链接映射、栈高水位、分配追踪、进程 RSS 和求解器结构计数回答不同问题，不能互相替代。
6. **观测最大值不是 WCET**：B2 报告 `observed_max`。只有明确假设下的静态时序分析或覆盖充分、带安全裕量且措辞限定的工程界限才能报告 `analysis_bound` 或 `engineering_bound`；均不得冒充飞行认证 WCET。

## 3. 方案选择

### 3.1 备选方案

- **方案 A：仅扩展现有 Python 主机 recorder。** 实现快，但 Python 无法可靠定义 C 内部阶段边界，目标板也未必有 Python；拒绝。
- **方案 B：只在 C 主程序打印汇总值。** 易移植，但丢失逐样本状态、环境和完整性链，无法独立重算；拒绝。
- **方案 C：C 采集器输出逐样本 JSONL，Python 校验、聚合和冻结。** C 负责接近被测代码的时钟与内存探针，Python 负责 schema、统计和证据完整性；采用。

方案 C 保持测量路径轻量，并使主机 Linux、ARM Linux SBC 以及后续 RTOS/裸机目标可以共享语义而非共享不适用的系统调用。

## 4. 组件与文件边界

Stage B2 实施应拆为以下单一职责组件：

- `experiments/benchmark_protocol_v2.schema.json`：host/target manifest 的 JSON Schema，固定计时范围、运行次数、时钟、目标身份、构建和调度条件。
- `experiments/benchmark_protocols/*.json`：每个设备与构建一份版本化 manifest。修改 CPU、频率、编译选项、求解器目标或计时方法即产生新 `benchmark_id`。
- `benchmarks/staged_benchmark.c`：独立驱动，执行预热与逐次测量，输出 JSONL；不承载统计逻辑，不修改手写矩阵来源属性。
- `benchmarks/benchmark_clock.h` 与平台实现：Linux 使用 `clock_gettime(CLOCK_MONOTONIC_RAW)`；目标板使用经校准、可证明无回绕歧义的单调硬件计数器。所有 tick 在记录中保存原值并显式转换为 ns。
- `benchmarks/allocation_probe.*`：测试构建专用的分配/释放计数和当前/峰值活动字节，不进入生产数值逻辑。
- `experiments/benchmark_contracts.py`：逐行 schema、跨字段不变量、样本完整性和平台协议校验。
- `experiments/aggregate_benchmark.py`：从 raw JSONL 重算分位数、观测最大值、失败分类和置信区间；不接受预先聚合输入。
- `experiments/memory_evidence.py`：解析链接 map/ELF section、栈高水位和分配追踪，输出带来源的内存证据。
- `tests/test_benchmark_v2_contract.py`、`tests/test_benchmark_aggregation.py`、`tests/test_memory_evidence.py`：协议、统计和内存解析的 adversarial tests。

现有 `experiments/benchmark_protocol.json`、`benchmark_host.py` 及其测试继续验证 Stage A 固定协议，不就地改变含义。B2 使用 v2 文件，避免历史证据被新字段静默重解释。

## 5. 计时范围

### 5.1 单次端到端状态机

每个 measured run 必须在同一线程、同一进程和同一次控制周期内按以下顺序执行：

```text
t0 -> 输入快照/数值矩阵更新 -> t1
   -> ECOS_setup                  -> t2
   -> ECOS_solve                  -> t3
   -> 状态检查/首控制量提取      -> t4
```

定义：

| scope | 计算 | 包含 | 不包含 |
|---|---:|---|---|
| `matrix_update` | `t1-t0` | 从固定导航输入更新数值数据、CRS→CCS（若本路径每周期执行） | 文件 I/O、JSON 序列化 |
| `setup` | `t2-t1` | `ECOS_setup()` 及其工作区分配、排序和符号准备 | 矩阵更新 |
| `solve` | `t3-t2` | 单次 `ECOS_solve()`，包括其内部迭代 | setup、结果提取 |
| `control_extract` | `t4-t3` | 状态分类、解审计所需轻量检查、首个控制指令复制 | 日志写盘 |
| `end_to_end` | `t4-t0` | 上述四段在同一次 run 内的完整在线路径 | 进程启动、离线数据加载、证据写盘 |

每行必须满足允许的定时器量化误差下 `end_to_end >= matrix_update + setup + solve + control_extract`。阶段时钟调用本身形成的间隙属于端到端但不属于四个阶段，因此不要求相等。聚合器禁止用四个阶段的 p99 之和生成端到端 p99；端到端分位数只从逐 run 的 `end_to_end` 原始值计算。

### 5.2 两种运行模式

- `cold_cycle`：每次 measured run 都执行 update、setup、solve、extract 和 cleanup，用于完整重规划成本；五个 scope 均必须测量。
- `persistent_workspace`：setup 在 measured loop 外只执行一次，每周期只更新允许变化的数据、solve 和 extract。此模式的 `setup` 必须为 `not_in_cycle`，`end_to_end` 只覆盖在线周期，且必须另记一次性 `initialization_ns`。只有实际 API 允许安全复用时才能启用。

两种模式是不同 `benchmark_id`，不得放进同一时延分布。若 ECOS 接口并不支持在保持数学等价的同时更新所需数据，`persistent_workspace` 必须记录为 `unsupported`，不能测一个不同问题。

### 5.3 采样和运行控制

- 每个 benchmark 固定 100 次 warmup、至少 10,000 次 measured run；资源受限目标若不能满足，manifest 必须记录预注册的较小样本数和理由，论文不得与 10,000 次数据作同精度比较。
- 保存所有逐次整数 tick/ns、状态、迭代数和审计分类；`outlier_policy = none`。
- Linux 测量记录 CPU affinity、调度策略/优先级、governor、最小/最大/观测频率、turbo/boost 状态、在线 CPU、负载、温度起止值。无法读取的字段为 `not_observed`，不能臆测“已关闭”。
- 目标板记录时钟树、固定/动态频率、cache/TCM 配置、RTOS 与 tick/中断配置。中断是否屏蔽必须显式记录；屏蔽中断的数据不能直接代表可部署调度时延。
- 单调计数器必须做分辨率、调用开销、回绕周期和频率校准。原始时间不得扣除平均计时开销；校准数据只用于解释测量下限。
- stdout/JSONL 写盘在 measured interval 外进行。缓冲区容量不足、计数器回绕歧义或样本丢失使整次 evidence `invalid`，不得只丢坏行。

## 6. 时间证据 schema 与统计

### 6.1 Manifest 必填字段

`benchmark_id`、`schema_version`、`evidence_kind`、`model_id`、`solver_id/version`、`implementation_id`（明确 `handwritten_legacy` 或自动验证路径）、`git_commit`、`executable_sha256`、`precision`、`build_type`、编译器及完整 flags、链接库摘要、run mode、warmup/measured runs、scope 定义、timer、设备身份、频率/功耗/散热/调度条件、超时阈值、审计容差和 raw 输出路径。

目标身份至少包含厂商/板卡、SoC/CPU、ISA、核心、RAM、OS/RTOS/固件版本。`target_measured` 禁止设备字段为 N150/x86；`host_measured_v2` 禁止 ARM/RISC-V/MCU 标签。设备类型由协议字段决定，不从营销名称推断。

### 6.2 每行必填字段

每行包含 `benchmark_id`、递增 `run_index`、`phase=measured`、五个 scope 的整数 tick/ns 或合法状态、`solver_status`、`iterations`、`audit_classification`、`deadline_miss`、温度/频率快照（平台支持时）和错误分类。输入保持固定时保存输入 digest；若做场景序列，则保存 `sample_id` 并由另一个预注册 manifest 定义，不能混为微基准。

### 6.3 汇总

对全体 measured attempts 报告分母和以下互斥计数：`audited_success`、`physical_violation`、`solver_infeasible`、`solver_error`、`timeout`、`measurement_error`。时间分布至少分两组：

1. `all_completed_attempts`：所有获得完整计时的尝试，包括数值或物理失败；
2. `audited_success_only`：仅用于诊断，不得替代第一组作为实时性结论。

每个 scope 报 `count/p50/p95/p99/p99.9/observed_max`，使用最近秩并在 manifest 中固定算法。另报 deadline miss 的分子、分母和 Wilson 95% 区间。不得删除 warmup 之后的首次样本、温度较高样本或调度抢占样本。

### 6.4 WCET 术语门槛

证据对象必须包含 `timing_assurance`，取值只能为：

- `empirical_distribution`：默认；允许写“10,000 次中的观测最大值”，禁止 `WCET`、`worst-case guarantee`、`hard real-time safe`。
- `engineering_bound`：需预注册输入域、覆盖论证、干扰模型、压力条件、观测最大值、明确安全裕量及独立复核；只能称“该假设集下的工程预算上界”，不是形式化 WCET。
- `static_analysis_bound`：需可审计的工具、版本、硬件模型、循环界、cache/总线/中断假设和分析报告；只能在这些假设内称 WCET 分析界。

普通 Linux 用户态 N150 或 SBC 数据只能是 `empirical_distribution`。`observed_max` 即使来自百万次运行也不自动升级。

## 7. 内存证据

### 7.1 指标与权威来源

| 指标 | 权威来源 | 限定 |
|---|---|---|
| `text/rodata/data/bss` | 最终 ELF + linker map，按 section 和符号归因 | 不能代表运行峰值 |
| 手写静态数组 | map/ELF 符号尺寸 | 必须与 solver workspace 分开 |
| 动态分配调用/峰值活动字节 | 分配探针包装 `malloc/calloc/realloc/free` | 仅测试构建；记录探针开销和线程假设 |
| 线程栈高水位 | 目标板填充模式/canary 或经验证的 OS API | 必须覆盖 setup、solve、错误和 cleanup 路径 |
| Linux RSS/PSS | `/proc` 或 `smaps_rollup` 的阶段快照 | 页粒度进程指标，不能称 ECOS 精确堆占用 |
| ECOS/LDL 结构量 | 运行时维度、nnz、symbolic/numeric fill counts | 是结构证据，不直接等于字节峰值 |
| 总 RAM 工程预算 | 静态区 + 栈界 + 堆峰值 + RTOS/系统保留 + 明示裕量 | 仅在同一目标构建内求和 |

### 7.2 测量生命周期

内存采集必须分别记录 `before_setup`、`after_setup`、`peak_solve`、`after_cleanup`。执行至少 10,000 次 setup/solve/cleanup 压力循环，并满足：活动分配字节和活动分配块在每轮 cleanup 后回到基线；任何单调增长都分类为 `memory_growth_detected`。

“solve 阶段零动态分配”要求分配探针证明 measured solve interval 内 `allocation_calls=0`，仅凭源码搜索不成立。“全生命周期无动态分配”还需 setup 和 cleanup 范围也为零，并由链接/符号检查排除未包装分配器。静态池改造不属于本设计的默认交付；若后续实现，必须作为独立 implementation id 与原始 ECOS 基线对比。

栈高水位需用已知填充值初始化整段可用栈，在最深路径后扫描，并保留 guard margin；递归、ISR 栈、其他线程栈分别报告。Linux 上 `ru_maxrss` 只能作进程级辅助证据，不能给出栈/堆拆分。

## 8. 平台矩阵

### 8.1 必需平台

1. **Intel N150 host baseline**：用于新 v2 协议的受控重复测量，仅支持本机特定构建结论。不得称为嵌入式目标证据。
2. **至少一种非 x86 实测目标**：优先选择仓库实际可访问、具备原生双精度支持的 ARM Linux SBC 或 RISC-V Linux 板。选择依据是可复现工具链、稳定时钟和足够内存，不预先承诺树莓派、Cortex-M 或某个性能结果。

### 8.2 可选平台与禁止外推

MCU/RTOS/HIL 是后续独立 evidence kind。没有实际板卡、交叉编译产物、运行日志和目标时钟校准时，只能列为 `candidate_platform`。N150、ARM SBC、RISC-V、MCU 的结果不得用频率比或 CoreMark 比例互相换算。每个平台都必须重新进行数值审计；能运行不等于结果正确。

## 9. 数据冻结与声明链

每个完成的 benchmark 形成：

```text
manifest.json
raw.jsonl
raw.jsonl.gz
summary.json
memory.json
build.map
provenance/ (compiler, cmake, cpuinfo/device-tree, config, hashes)
```

冻结清单保存所有文件 SHA-256、行数和大小上限。confirmation 检查流式验证 raw/gzip 一致性、逐行 schema、manifest digest、summary 可重算性、可执行文件 digest 和 claim ledger 绑定。权威文件缺失、样本数不足、未知状态或 digest 不符必须失败，禁止降级为 warning 后进入论文。

论文表图只能读取已冻结 summary。声明至少包含平台、构建、精度、run mode、scope、样本数和 assurance 等级。例如合法表述是“在指定 N150/Linux/Release 构建的 10,000 个完整在线周期中，观测 p99 为 X ms、最大值为 Y ms”；非法表述是“ECOS WCET 为 Y ms”或“在 Cortex-M 上预计满足 10 Hz”。

## 10. 错误处理和失败分类

- 时钟非单调、计数器回绕不明确、样本缺失、JSON 行截断：`measurement_error`，整组 confirmation 失败。
- 超时：保留截止时的完整可用阶段时间和 solver 状态，分类 `timeout`；不重跑替换原样本。
- 求解器失败或物理审计失败：保留计时，进入 `all_completed_attempts`，但不得进入成功燃耗统计。
- 温度、频率或调度元数据不可读取：字段 `not_observed`；证据仍可作为经验分布，但不得声称受控条件。
- 目标板复位/看门狗：写入独立 host-side run ledger，并与板端最后持久化 run index 对账；缺口不得静默忽略。

## 11. 测试策略

实施必须采用 TDD，并至少覆盖：

1. schema 拒绝未知字段、错误 evidence kind、平台伪装、缺少构建 flags、浮点 ns、重复/缺失 run index 和错误 scope 状态；
2. 同一 run 的时间不变量、`not_in_cycle` 仅允许 persistent mode、禁止由阶段分位数合成端到端分位数；
3. 最近秩 p50/p95/p99/p99.9 边界、重复值、大整数和所有失败分类分母守恒；
4. `observed_max` 不生成 `wcet_ns` 字段，普通经验协议拒绝 WCET/guarantee 标签；
5. raw/gzip/summary digest、行数、大小上限和流式重算；
6. map parser 对 GNU ld/lld 的固定 fixture、section 重复名、十六进制溢出、缺失符号和恶意超大输入；
7. allocation probe 的 realloc、失败分配、double free 检测、cleanup 回基线和 solve interval 零分配判据；
8. 栈高水位边界、canary 破坏和未覆盖路径使证据无效；
9. 使用最小 C fixture 校验计时器单调性、JSONL 格式和 probe 开关不改变数值输出；
10. 手写资产保护测试继续通过，并确认新 benchmark target 链接手写源而非生成数据，但不修改其内容。

测试 fixture 使用合成数据，不把当前机器的时延阈值写进 CI。quick CI 只验证契约和最小运行；冻结 confirmation 才检查指定设备结果的完整性，硬件不可用时明确报告 evidence unavailable，不能伪造通过。

## 12. 分阶段交付

### B2.1 协议与离线验证

建立 v2 schema、聚合器、内存 parser、adversarial tests 和冻结检查。完成条件：合成证据可重算，错误平台/范围/WCET 术语被拒绝，Stage A 测试不回归。

### B2.2 N150 受控主机基线

实现 C staged benchmark，采集 cold-cycle 与可行时的 persistent-workspace 原始样本，记录调度/频率/温度及内存证据。完成条件：10,000 条逐次记录、全状态审计、p99/p99.9/观测最大值、setup/solve/end-to-end 分离、无未经测量的控制条件声明。

### B2.3 非 x86 目标实测

选择实际可用目标板，冻结交叉/原生工具链和目标 manifest，重复数值、时间和内存审计。完成条件：至少一种非 x86 板产生可确认的 raw/summary/memory/provenance 证据；否则 Stage B2 保持未完成，论文只写未来工作。

### B2.4 论文接入

通过 claim ledger 接入冻结数字，生成统一口径的 scope 图和内存预算表。完成条件：所有定量文字和图表由 evidence 重建，明确 `empirical_distribution`，不把观测最大值写成 WCET。

## 13. 验收门槛

Stage B2 只有同时满足以下条件才可宣告完成：

- Stage A 的 132 项单测、quick/confirmation 和手写资产保护继续通过；
- N150 v2 与至少一种非 x86 目标各有独立 manifest、原始逐次时间、可重算统计、数值审计和内存证据；
- setup、solve、end-to-end 的边界和运行模式明确，任何 `not_measured/not_observed/unsupported` 均保留；
- 报告 p50/p95/p99/p99.9/观测最大值及全部失败分母，不删除异常值；
- 链接静态区、堆峰值、栈高水位和 LDL 结构量分别有来源，未测指标不以估算替代；
- 没有 N150 到 ARM/MCU 的性能外推，没有将经验最大值称为 WCET；
- 论文数字均绑定冻结 digest，PDF 图表经过最终视觉审查；
- `MarsLanding/MarsLanding.c` 内容和人工来源属性未被改动或弱化。

## 14. 明确不在本设计内

- 飞行认证、DO-178C/ECSS 合规或形式化 WCET 认证；
- 根据 N150 推算树莓派、MCU 或 RISC-V 性能；
- 默认修改 ECOS 为静态内存池、宣称无 malloc 或改变求解算法；
- 用 Stage B2 基准替换 Stage B1 的物理修正、自由终端时间和网格收敛研究；
- 修改论文结论前先产生未经冻结的“漂亮数字”。
