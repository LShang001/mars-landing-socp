# 手写矩阵资产来源与维护边界

`MarsLanding/MarsLanding.c` 是作者 LShang001 原始、独立实现的 SOCP 手写矩阵资产。它直接构造 CRS 稀疏矩阵，再通过 `CRM2CCM.c` 转换为 ECOS 使用的 CCS 格式；这条实现路径不是从 CasADi 数据生成或回填得到的。

`MarsLanding/MarsLandingAuto.c` 与 `MarsLandingAutoData.h` 属于自动建模路径，仅用于交叉验证手写实现的物理结果、维度和求解结果。自动版不能成为手写版的矩阵数据来源，也不能替代手写版的构造逻辑。

## 允许的修改

- 修正手写构造中的明确缺陷，并保留 CRS→CCS 独立实现。
- 修改物理参数时，同步更新参数来源和一致性校验。
- 改进注释、诊断和测试，但不得改变资产来源属性。

## 禁止的修改

- 在 `MarsLanding.c` 中包含 `MarsLandingAutoData.h` 或其他生成矩阵数据。
- 将 `ecos_avx` 或 `ecos_scalar` 改为自动生成矩阵路径。
- 用自动生成数组替换、覆盖或静默同步手写矩阵条目。
- 以文件哈希冻结手写源；保护对象是实现边界和可审查的来源关系，而不是某个不可修改的字节快照。

## Review 要求

涉及手写矩阵、CMake 源文件分组或自动生成路径的变更，review 必须确认：`USER_SOURCES` 仍包含 `MarsLanding.c` 和 `CRM2CCM.c`；`ecos_avx`、`ecos_scalar` 仍从 `ALL_SOURCES` 构建；`ecos_auto` 明确使用 `MarsLandingAuto.c`；手写源未引入生成矩阵数据。提交前运行 `python3 MarsLanding/check_model_consistency.py` 和对应单元测试，并结合 400.7 kg 黄金基准审查数值行为。
