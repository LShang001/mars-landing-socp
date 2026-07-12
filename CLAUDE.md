@AGENTS.md

# Claude Code 专属配置

## 提交规范
- 提交信息使用中文描述 + 类型前缀 (feat/fix/doc/refactor)
- 提交前运行 `./build/bin/ecos_avx | grep 燃料` 确认 400.7 kg
- Co-Authored-By: Claude <noreply@anthropic.com>

## 偏好设置
- 中文交流，结论先行
- 技术决策自主做，仅破坏性操作需确认
- 代码改动前多轮审查，不边改边试
- 新经验沉淀到 `AGENTS.md` 陷阱节和 `docs/` 目录

## 关键检查点
- 修改 C 代码后: `cd build && make -j4 && ./bin/ecos_avx | grep 燃料`
- 修改 Python 后: `cd MarsLanding && python3 mars_solve.py`
- 修改矩阵构造后: `python3 mars_model.py` 验证非零元+数值
