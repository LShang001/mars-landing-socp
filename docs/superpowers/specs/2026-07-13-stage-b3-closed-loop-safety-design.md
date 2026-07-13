# Stage B3/B4 闭环重规划、故障注入与安全降级设计

## 1. 目的与证据边界

本阶段把 Stage A 的单次开环 Monte Carlo 扩展为可重放的闭环 episode，回答三个彼此独立的问题：在模型和导航误差下能否安全着陆；求解不可行或超时后能否按确定规则降级；执行器或传感器故障发生后，系统是否在限定时间内检测、隔离并进入风险更低的状态。

本设计只建立 3-DOF 平动闭环仿真、software-in-the-loop（SIL）证据，以及后续 hardware-in-the-loop（HIL）使用的接口契约。它不构成 6-DOF 姿态耦合、高保真发动机模型、飞行认证或 WCET 证明。论文只能按实际完成层级表述结论。

`MarsLanding/MarsLanding.c` 始终是作者原始、独立、人工维护的 `legacy_tf81_v1` 手写 CRS→CCS 参考实现。闭环 runner、故障模型和自动参数化研究模型不得生成、覆盖或替代该文件。手写基准可以作为独立求解路径参与无故障回归，但 B3/B4 的参数化闭环功能在新模块中实现。

## 2. 已选方案与备选方案

采用“确定性离散事件仿真 + 一条 episode JSONL + 独立审计器”的方案。它复用 Stage A 的 manifest 哈希、不可变发布和失败不删样本原则，同时允许逐周期重放状态估计、求解结果、控制命令、故障事件和状态机转移。

未采用的两种方案：

1. 仅保存 episode 末端摘要。文件小，但无法证明故障检测时刻、超时后是否仍使用过期控制，也无法独立重算安全指标。
2. 一开始引入通用连续时间/6-DOF 仿真框架。保真度潜力更高，但会同时改变动力学、控制分配、导航和求解器接口，无法隔离 B3 的闭环机制效应。

B3 固定采用零阶保持、固定仿真步长、固定制导周期、确定性事件顺序。B4 在相同协议之上替换 plant 或 I/O transport，保持状态机、故障 taxonomy 和证据格式不变。

## 3. 分层架构

```text
版本化 episode manifest
        |
        v
确定性 sampler -----> fault schedule
        |                    |
        v                    v
 plant truth -> sensors -> navigation estimate -> supervisor/state machine
     ^                                               |
     |                                               v
 actuator <- command limiter <- guidance adapter <- planner
        |
        v
逐周期 event JSONL -> 独立 episode auditor -> summary/置信区间 -> claim ledger
```

建议文件边界如下；本规范不要求本轮实现：

- `experiments/closed_loop/contracts.py`：manifest、episode header、step、footer 的严格 schema。
- `experiments/closed_loop/scenario_loader.py`：哈希、分层 seed 和故障时间表生成。
- `experiments/closed_loop/plant.py`：3-DOF truth propagation；不包含 supervisor 逻辑。
- `experiments/closed_loop/faults.py`：纯函数故障注入和故障状态。
- `experiments/closed_loop/supervisor.py`：唯一闭环状态机和降级决策所有者。
- `experiments/closed_loop/guidance.py`：ECOS/Clarabel/手写基准适配接口；不吞掉状态码。
- `experiments/closed_loop/run_episodes.py`：确定性事件循环、逐条 fsync 和原子发布。
- `experiments/closed_loop/audit.py`：只读重算，不信任 runner 给出的 success。
- `experiments/closed_loop/aggregate.py`：episode 级统计、置信区间和故障条件统计。

## 4. 版本化场景合同

闭环 manifest 使用新 `schema_version: 2` 和 `kind: closed_loop_monte_carlo`，不得把新增字段塞进 Stage A 的 v1 合同。任何字段变化都产生新 `scenario_id`；禁止在同一 ID 下修改阈值、故障范围或样本数。

必需顶层字段：

| 字段 | 含义 |
|---|---|
| `schema_version`, `scenario_id`, `kind` | 合同版本和不可复用场景标识 |
| `master_seed`, `episode_count` | 总 seed 与总分母 |
| `model` | plant/guidance 模型 ID、坐标系、质量/推力/重力参数集 ID |
| `timing` | `plant_dt_s`、`guidance_period_s`、`deadline_s`、最大仿真时间 |
| `initial_conditions` | 标称真值及版本化分布 |
| `navigation` | 采样率、延迟、偏置、噪声和丢包模型 |
| `environment` | 重力、风/大气或未建模加速度的分布；未启用项必须显式为 `none` |
| `actuation` | 时延、幅值误差、方向误差、速率限制和发动机配置 |
| `fault_campaign` | 故障类别、严重度层、注入窗、组合规则和无故障对照占比 |
| `planner` | adapter、solver、模型版本、网格、终端时间策略、容差和迭代上限 |
| `supervisor` | 检测阈值、去抖周期数、恢复规则、降级控制参数 |
| `success_criteria` | touchdown、走廊、质量、碰撞和响应时限阈值 |
| `provenance_requirements` | 代码、依赖、平台、构建和 manifest digest 要求 |

随机流使用 `SeedSequence(master_seed).spawn(...)` 或等价的固定分层派生，至少分离 `initial_state`、`navigation`、`environment`、`actuation`、`fault_schedule` 五个子流。添加新的噪声源不得改变已有子流的样本序列。每个 episode 记录全部派生 seed 和抽样后的实际参数，而不只记录分布。

场景阶梯必须分别冻结，不能用同一数据集事后筛选：

| 层级 | 内容 | 目的 |
|---|---|---|
| `CL0` | 无噪声、无故障 | 闭环与开环/独立求解器回归 |
| `CL1` | 初值、导航、质量、重力和执行误差 | 一般闭环鲁棒性 |
| `CL2` | 单一故障，每个类别和严重度分层 | 故障检测与降级归因 |
| `CL3` | manifest 预先列出的双故障组合 | 交互作用和失效边界 |
| `CL4` | 相同合同的 HIL transport/真实目标执行时延 | 平台闭环证据 |

确认性 campaign 在探索实验结束后冻结。故障类别、严重度、注入窗和 episode 数必须在运行前确定；失败 episode、未触发故障 episode 和 solver 异常都保留在预先定义的分母中。

## 5. 扰动与故障 taxonomy

扰动是全 episode 有效的随机参数或噪声过程；故障是在明确时刻改变组件行为的离散事件。两者禁止混称。

### 5.1 连续扰动

- 初始位置、速度、质量误差。
- 导航白噪声、常值偏置和有界相关噪声；必须记录生成模型和相关时间。
- 重力缩放误差、恒定/分段常值未建模加速度。
- 推力幅值比例误差、方向小角误差、执行时延和指令速率限制。

分布必须显式写出类型、单位、参数和截断边界。不允许使用“典型噪声”或未版本化的外部默认值。

### 5.2 离散故障

| 域 | `fault_type` | 严重度参数 | 最低可观测证据 |
|---|---|---|---|
| 执行器 | `engine_loss`, `thrust_derate`, `thrust_stuck`, `thrust_direction_bias` | 失效台数、剩余比例、保持值、角度 | 真值生效时刻、检测时刻、可用推力包络 |
| 导航 | `measurement_dropout`, `measurement_freeze`, `position_bias_step`, `velocity_bias_step`, `timestamp_delay` | 时长、偏置、延迟 | 原始测量、有效性标志、估计状态、innovation |
| 计算 | `solver_timeout`, `solver_infeasible`, `solver_numerical_error`, `deadline_miss` | 连续周期数、注入状态码或延迟 | 开始/结束时间、deadline、原始求解状态 |
| 通信/HIL | `input_frame_loss`, `output_frame_loss`, `stale_frame`, `checksum_error` | burst 长度、延迟、损坏字段 | sequence ID、时间戳、校验结果 |

`solver_infeasible` 只在求解器确实返回不可行时使用；进程异常、数值错误和超时不能改标为物理不可行。注入的 solver 错误与自然发生的 solver 错误由 `origin: injected|observed` 区分。

每个故障事件包含 `fault_id`、`fault_type`、`domain`、`origin`、`scheduled_time_s`、`effective_time_s`、`duration_s|null`、严重度参数和 `injection_status`。若 episode 在注入前终止，记录 `not_reached`，仍计入 campaign 总分母，并在“已实际暴露”条件分母中另行报告。

## 6. 闭环事件顺序与状态机

每个 plant tick 的顺序固定为：完成上一周期执行器动态；推进 truth；生成并故障化传感器帧；更新导航；运行监视器；若到制导边界则调用 planner；依据 deadline 和状态码原子接受或拒绝计划；状态机选择命令；限幅/控制分配；记录 step。相同时间戳的故障在传感/执行组件读取前生效。该顺序属于 manifest 所引用的 `event_order_version`。

状态机状态：

| 状态 | 含义 | 允许动作 |
|---|---|---|
| `INIT` | 等待首个有效导航解 | 不输出规划推力；超过初始化时限即 `ABORT` |
| `NOMINAL` | 新计划有效且健康监视正常 | 执行带时间戳的新命令 |
| `HOLD_LAST` | 单次 timeout/error/dropout | 仅在 `command_valid_until` 内保持最后一条已审计命令 |
| `REPLAN_DEGRADED` | 连续异常或执行器能力变化 | 用更新后的能力包络重规划，并收紧命令有效期 |
| `TERMINAL_SAFE` | 低高度且重规划风险高 | 执行预定义、限幅且可审计的末端安全控制律 |
| `ABORT` | 已无可证明安全的控制权限 | 输出 manifest 定义的最小风险命令并锁存 |
| `LANDED` | touchdown 条件满足 | 推力关闭，episode 终止 |

所有转移只能由 `supervisor.py` 的纯决策函数产生，并记录 `from_state`、`to_state`、`reason_code` 和触发量。禁止 planner adapter 直接决定降级。

默认转移语义如下，具体数值由 manifest 固定：

- `INIT -> NOMINAL`：导航有效且首个计划通过数值与物理审计。
- `NOMINAL -> HOLD_LAST`：首次 deadline miss、solver error 或短时导航无效。
- `HOLD_LAST -> NOMINAL`：下一有效计划通过审计；不得仅因 solver 报 `optimal` 恢复。
- `HOLD_LAST -> REPLAN_DEGRADED`：异常达到去抖计数，或确认执行器能力下降。
- `REPLAN_DEGRADED -> NOMINAL`：能力约束已更新且连续两个计划有效。
- 任意飞行态 `-> TERMINAL_SAFE`：高度进入 terminal gate 且计划不可用，但导航仍有效、预定义控制律在当前推力包络内。
- 任意飞行态 `-> ABORT`：命令过期、导航无效超过上限、无可用推力包络、状态非有限、预测撞地早于下次可恢复时刻，或降级重规划超过最大次数。
- 任意飞行态 `-> LANDED`：首次地面交叉经事件插值后满足 touchdown 判据；触地后不允许恢复到飞行态。

`HOLD_LAST` 不是无限期容错。每条命令带单调 sequence、生成时刻和 `valid_until`；过期后必须转移，禁止重复执行 stale command。`ABORT` 在火星下降中不表示“任务可挽回”，只表示确定、锁存、可审计的最小风险行为，因此统计中仍属于任务失败。

## 7. 逐 episode 证据合同

单个 JSONL 文件按以下顺序写入，每行均严格校验、包含 `scenario_id`、`episode_id`、manifest SHA-256 和递增 `record_seq`：

1. 一条 `episode_start`：实际抽样参数、派生 seeds、故障时间表、完整 provenance。
2. 一条或多条 `step`：时间、truth、measurement、estimate、planner invocation、solver 原始状态、耗时、deadline、计划审计、supervisor 状态、原始/限幅/实际命令、活动故障和累计资源计数。
3. 恰好一条 `episode_end`：终止原因、runner 初步分类和累计量。

大数组不允许塞进单个 step。规划轨迹写入内容寻址的 sidecar（例如压缩 NPZ），step 只保存 SHA-256、shape、dtype 和相对 artifact ID；审计器校验 digest 后读取。JSONL 与 sidecar 都采用新文件、临时文件 fsync、硬链接发布和父目录 fsync，不覆盖既有证据。

错误文本使用枚举 `error_type` 和经过长度限制的非敏感 `diagnostic_code`，不记录任意异常字符串、环境变量或绝对私有路径。HIL 记录额外包含设备 ID、固件 commit、build digest、时钟源、transport sequence 和主机/设备时间同步误差。

episode 级分类互斥且由独立 auditor 重算：

- `mission_success`：满足全部 touchdown、安全、质量和合同完整性条件。
- `controlled_failure`：未成功着陆，但进入并保持规定降级状态，没有发生危险事件。
- `unsafe_touchdown`：触地但速度、倾角代理或位置超限。
- `ground_collision`：安全走廊外地面交叉或非允许触地。
- `constraint_violation`：飞行中推力、质量、走廊或非有限状态超限。
- `stale_command_hazard`：命令在有效期后仍实际施加。
- `fault_response_violation`：故障检测、隔离或降级响应超过 manifest 限值。
- `simulation_error`：事件流、plant 或审计无法完成。
- `solver_exhaustion`：在未产生上述危险事件前耗尽允许的 planner 恢复次数。

优先级为危险事件类、`fault_response_violation`、`solver_exhaustion`、`controlled_failure`、`mission_success`；若多个危险事件发生，主分类使用最早危险事件，`secondary_events` 保留其余事件。失败记录不得省略实际输入、活动故障、最后有效状态和最后命令。

## 8. 独立审计指标

auditor 从 truth 和事件流重算，不接受 runner 的布尔 success。至少输出：

- 终端位置误差、垂直/水平/总触地速度和触地质量。
- 全程最小高度、最大走廊违反、推力幅值违反、推力速率违反、质量下界违反。
- planner 调用数、有效计划数、各状态驻留时间、最长连续失败周期。
- 每个故障的 schedule/effective/detected/isolated/mitigated 时间及对应 latency。
- deadline miss 次数、最长 solve time、过期命令施加时长。
- 燃料、飞行时间、降级重规划次数和 terminal-safe 启用次数。
- 合同完整性：时间单调、sequence 连续、唯一 footer、sidecar digest、状态转移合法性。

所有安全阈值必须在 manifest 中给出 SI 单位。首个实现的保守测试阈值建议作为 `closed_loop_baseline_v1` 明确冻结，而非写死在代码：触地总速度不高于 `2.0 m/s`、水平速度不高于 `1.0 m/s`、位置误差不高于 `5.0 m`、质量不低于 `1505.0 kg`、走廊与推力违反不高于审计容差。最终论文阈值必须由任务需求或可引用来源支持；在此之前只能称为项目验收阈值。

## 9. 统计设计与门槛

统计单位是 episode，不是 guidance tick。主结果必须同时报告总分母、实际暴露分母、分类计数、比率及 Wilson 95% 区间。`mission_success`、`safe_outcome = mission_success + controlled_failure` 和各危险分类分别报告，不得只报告条件成功样本。

每个单故障类别和严重度层独立分层。必须提供与其共享相同初值/扰动样本的无故障 paired control；报告成功率差、paired outcome 转移表、燃料和终端误差差值。连续指标报告中位数、p95、p99、最大值和 bootstrap 95% 区间；样本过少时明确标为探索性，不输出伪精确 p99。

门槛分三层，防止“没观察到失败”被误写为证明安全：

### 9.1 CI contract smoke

- 每个必需 fault domain 至少一条确定性 episode；只卡 schema、重放一致性、审计器能发现人工植入危险、记录数和状态转移合法性。
- smoke 不以成功率卡 CI，也不产生论文结论。

### 9.2 探索性 campaign

- 每个故障类别/严重度至少 100 个实际暴露 episode，并带 paired control。
- 用于定位边界和冻结确认性方案，不作为最终安全概率声明。

### 9.3 确认性 campaign

- 每个预声明分层至少 1000 个实际暴露 episode；总 episode 数由注入窗未到达比例预先上调，不能运行后补齐“好看”的层。
- 合同、manifest/raw/sidecar/summary digest、代码 commit 和环境冻结方式与 Stage A confirmation 相同。
- `stale_command_hazard`、非法状态转移、非有限命令和证据合同损坏的允许计数均为 0；出现 1 次即门槛失败并保留样本。
- 对有可恢复能力的单故障层，预注册验收目标为 `safe_outcome` 的 Wilson 95% 下界不低于 `0.99`，且故障响应超时计数为 0。
- `mission_success` 不设跨故障统一阈值；每层在确认实验前依据物理可恢复域单独冻结。不可恢复故障仍要求确定降级，但不能包装为安全着陆成功。
- deadline 要求按目标平台单独冻结；SIL 主机耗时不得替代 HIL/目标平台 deadline 证据。

若 1000/1000 成功，Wilson 95% 下界约为 0.996；因此 1000 样本足以检验 0.99 的下界门槛。任何更高可靠性或飞行安全概率结论都需要相应样本规模、稀有事件方法和系统安全论证，本阶段不作此声明。

## 10. 验证、消融与反例测试

实现必须按 TDD 推进，至少包括：

1. 合同拒绝未知字段、非有限值、非单调时间、重复 sequence、错误 digest 和缺失 footer。
2. 固定 manifest 两次运行逐字节一致；添加一种新噪声流不改变旧子流。
3. 解析解或高精度积分器验证 plant；零推力时重力符号必须与 x 轴向上约定一致。
4. 故障在同一事件顺序版本下恰好于计划时刻生效，短 episode 产生 `not_reached`。
5. 状态机表驱动测试覆盖每条合法转移；非法转移、过期命令和恢复去抖不足必须失败。
6. auditor 对 runner 声称 success 但存在干重、走廊、触地速度或 stale-command 违反的记录判失败。
7. solver timeout、不可行、数值异常和注入错误保持不同分类。
8. 聚合器拒绝混合 scenario/digest、重复 episode、缺失分层，并从 raw 重算 summary。
9. fault-off 回归与独立 ECOS/Clarabel 路径一致；手写 `legacy_tf81_v1` 仅作为明确标识的独立基准，不被参数化闭环路径冒名。
10. paired 消融至少比较：不开重规划、只 hold-last、重规划但无降级、完整 supervisor；这样才能归因安全响应收益。

验证阶梯是 `CL0 -> CL1 -> CL2 -> CL3 -> CL4`。前一层的合同和数值回归未通过，不得用后一层结果支持论文 claim。CL4 还必须故意注入迟到帧、乱序帧、checksum error 和设备超时，确认 transport 故障不会静默变成有效控制命令。

## 11. 实施顺序与停止条件

1. 先实现 v2 合同、确定性 sampler、最小 plant 和 event log，不接求解器。
2. 实现 supervisor 纯状态机及 table-driven 反例测试。
3. 接入一个参数化规划 adapter，完成 CL0 数值回归和独立审计。
4. 加入连续扰动完成 CL1 paired baseline。
5. 按执行器、导航、计算、通信顺序逐类加入单故障；每类先通过反例测试再运行探索 campaign。
6. 冻结 CL2/CL3 confirmation manifests 后生成不可变证据。
7. 只有 SIL 的 deadline、状态机和证据链稳定后，才将同一接口连接 HIL transport 进入 CL4。

出现以下任一条件立即停止 campaign 并保留已生成 evidence：非有限 truth/command；非法状态转移；stale command 实际施加；manifest digest 漂移；sidecar digest 错误；episode 丢失 footer；runner 与 auditor 分类不一致。停止后先修复合同或实现并创建新 scenario ID，禁止覆盖失败数据或在原 manifest 下续跑混合版本。

## 12. 文档与声明纪律

- 经验沉淀应补充到 `docs/` 和 `AGENTS.md`：事件顺序、状态机所有权、故障/扰动区别、stale command 禁令和确认性统计门槛。
- claim ledger 必须绑定 manifest、raw JSONL、全部 sidecar、summary、auditor 版本和 commit digest。
- 图表只读取审计后的 summary；故障响应时间线可读取通过 digest 校验的代表性 episode，但选择规则必须预先定义（例如每层最接近中位数的 episode），不能挑最好轨迹。
- “安全”“实时”“鲁棒”“容错”均限定到具体场景、平台、故障集合和阈值。SIL 通过只能表述为仿真证据；HIL 通过也不能外推为飞行认证。

## 13. 规范自审结论

本规范无待定字段。数值阈值区分了项目建议值与待来源支持的任务需求；统计分母、未触发故障、solver 错误、受控失败和危险失败均有明确处理；SIL、HIL、6-DOF 和飞行认证边界互不混淆。设计不修改核心求解代码、论文或 `MarsLanding/MarsLanding.c`，也不改变 Stage A 已冻结的 v1 evidence。
