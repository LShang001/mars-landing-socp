# 阶段 A 证据基线完成审计

## 审计结论

- 审计日期：2026-07-13（Asia/Shanghai）
- 审计提交：`554542b41c33a407615de1b2070c6a9dae974337`
- 结论：`DONE_WITH_CONCERNS`
- 阶段 A 的场景契约、逐样本证据、冻结数据、声明台账、CI 门槛和手写资产保护已通过本轮审计。
- 阶段 A 完成仅表示证据基础设施基线完成，不表示长期研究目标完成，也不证明目标硬件实时性、HIL、闭环飞行就绪性或顶级期刊接收。

## 新鲜验证证据

以下命令均在上述提交、当前工作区中运行并退出 0：

```bash
python3 -m unittest discover -s tests -v
bash ci/validate.sh --quick
bash ci/validate.sh --confirmation
python3 paper/evidence/check_claims.py
python3 research/literature/check_literature.py
python3 research/literature/check_literature.py --verify-online
python3 MarsLanding/check_model_consistency.py
pdfinfo paper/mars_landing_socp.pdf
rg -n "Overfull|Underfull|undefined|Warning" paper/mars_landing_socp.log
sha256sum experiments/scenarios/near_nominal_v1.json \
  experiments/results/near_nominal_v1.jsonl \
  experiments/results/near_nominal_v1.jsonl.gz \
  experiments/results/near_nominal_v1.summary.json \
  paper/mars_landing_socp.pdf
wc -l experiments/results/near_nominal_v1.jsonl
git diff --check
```

结果摘要：

- unittest：132/132 通过；`--quick` 内再次通过 132/132，并通过 24/24 手写资产测试。
- 数值 golden：`ecos_avx`、`ecos_scalar`、`ecos_auto`、`ecos_clarabel`、CVXPY+ECOS、CVXPY+Clarabel、CasADi+IPOPT 均报告 400.7 kg。该结果只证明目标值回归，不替代物理可行性审计。
- `--quick`：claim checker、模型一致性、手写资产、七条数值路径与固定 8 样本 contract smoke 全部通过。
- `--confirmation`：冻结证据存在性、digest、1000 条逐行 schema、gzip/raw 逐字节一致性及重算 summary 比对全部通过。
- claim checker：通过。
- 文献矩阵：离线与在线复核均通过，40 个已验证来源、6 个主题。在线结果依赖审计时网络可达性，不是离线复现保证。
- 模型检查：尺寸、物理参数和手写矩阵资产边界通过。
- `git diff --check`：通过。

## 冻结数据与摘要

| 资产 | SHA-256 |
|---|---|
| scenario manifest | `c985c50f262eec4fbb6afdeda589cf2f38839c3fc90153430700f9fd56c14a76` |
| raw JSONL | `0e8acef4695f6d7d6a54fb04b5b6dabdf063e04b9e7cbc234a64387589319a47` |
| deterministic gzip | `7fbe7e4eda2d06a26d6a9bebbcabb6c13551477f485e3e14e905b34814287760` |
| summary JSON | `afc6249877f30957519608e156dd4a452d697652bb5c73aed86d3cb034176bae` |
| manuscript PDF | `8cbd2341bf3595c486cb52c21a2f039471077bdb26eaf57330c48fb35f77b032` |

JSONL 实际为 1000 行，与 manifest 的 `sample_count=1000` 和 summary 的
`attempted=1000` 一致。分类为成功 483、物理违反 363、求解器不可行 153、
求解器错误 1，合计 1000；成功率 0.483，Wilson 95% 区间
`[0.45215246974959655, 0.5139776400389123]`。燃料统计仅包含 483 个审计成功样本：
均值 383.8377679589953 kg，样本标准差 9.52401057392018 kg，范围
360.21576888446793--399.9547244292921 kg。论文声明台账把这些值绑定到冻结摘要，
confirmation 又从 raw JSONL 重算并逐字节比较摘要，因此失败样本没有从分母或条件统计语义中被隐去。

## PDF 与构建资产

`paper/mars_landing_socp.pdf` 为 50 页 A4、1,090,583 bytes。日志没有
`Overfull`、`Underfull` 或 undefined 告警；仍有两条 Fandol 字体字形警告和两条
hyperref PDF-string Unicode 警告，列为版式已知限制。

`CMakeLists.txt` 的 `USER_SOURCES` 仍明确包含 `MarsLanding/MarsLanding.c` 与
`MarsLanding/CRM2CCM.c`，`ecos_avx`/`ecos_scalar` 均来自 `ALL_SOURCES`；
`ecos_auto` 独立使用 `MarsLanding/MarsLandingAuto.c`。手写 `MarsLanding.c` 不引用
`MarsLandingAuto.c`、`MarsLandingAutoData.h` 或生成数据路径，自动生成实现没有替代
独立手写 CRS→CCS 参考资产。

## 关注项与限制

- 标称 CVXPY+ECOS 审计燃料为 400.7278765 kg、终端质量 1504.2721235 kg，违反 1505 kg 干质量下界 0.7278765 kg，分类为 `physical_violation`。因此 400.7 kg 不能宣称为满足全部物理约束的确认性解。
- 冻结 Monte Carlo 仅有 48.3% 审计成功率，包含 363 个物理违反、153 个不可行和 1 个尚未解决的求解器错误；它不是鲁棒性通过证据。
- Intel N150 证据仅为 Release `ecos_avx` 在矩阵装配和 `ECOS_setup` 之后的 1000 次 `ECOS_solve` CPU 时间均值 7.361 ms。没有逐次原始样本、分位数、p99、最坏值、WCET、端到端重规划、功耗或实时调度证据，也不得外推到 ARM、树莓派、MCU、RTOS 或飞行硬件。
- 当前证据不覆盖目标硬件交叉编译、静态内存、HIL、导航/执行器故障、闭环重规划、安全降级、6-DOF 或飞行就绪性。
- 当前工作区有未跟踪文件：`output.json`、`paper/mars_landing_socp.aux`、`paper/mars_landing_socp.blg`、`paper/mars_landing_socp.log`、`texput.log`。它们未被纳入冻结证据或本次文档修改。
- 本审计不构成同行评审结论，也不证明或承诺顶级期刊接收。
