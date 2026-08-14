# 命令、产物与检查范围

VibeFlow 的公开命令分别报告结构、质量、构建、审核产物或执行证据。JSON 保留 `status`，并提供 `result_code`、`validation_scope`、`summary`、`checked` 和 `not_checked`。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 更新 Architecture | `python run.py architecture --config <config> --output <root>/ARCHITECTURE.jsonc` |
| 检查 Architecture 新鲜度 | 在上述命令后添加 `--check` |
| 静态结构检查 | `python run.py validate --config <config>` |
| 项目质量检查 | `python run.py quality --path <root>` |
| 正式审核图 | `python run.py review --config <config> --output reports/workflow.svg` |
| Python 执行 | `python run.py run --config <config> --input <input.json>` |
| JavaScript AOT | `python run.py build --config <config> --target node --profile esm-module --out-dir <dir>` |
| 内核完整性 | `python run.py verify-kernel` |

`review` 生成并校验审核产物。collaborative profile 中，产物成功仍需后续人工批准；autonomous profile 按任务直接完成适用门禁。

## 检查范围

一次命令的 `checked` 只列出实际完成的阶段。结构检查可以覆盖：

- 配置和登记关系；
- Node 契约形状；
- 数据可达性；
- 控制流；
- 副作用边界；
- 实际执行的项目结构检查。

quality、build 和 review 会增加各自实际完成的检查。失败或无法取得证据的阶段不会写入 `checked`。

VibeFlow 命令不检查：

- 业务结果正确性；
- 项目需求符合性；
- 外部接口业务语义；
- 领域数据正确性。

这些结论由项目测试、集成测试和真实环境验收提供。

## 工作流执行探针

执行探针与静态 validate 分开运行。它只在有证据时报告：

- 工作流成功启动；
- Node 按编译计划执行；
- 声明的最终输出已经产生；
- 执行中没有结构性错误。

Python `run` 会在 run 目录写入 `workflow_execution_report.json`。JavaScript 最小项目先完成 AOT build，再导入生成入口并由 `scripts/workflow_execution_probe.mjs` 生成同形报告。

## 运行产物

Python run 目录包含健康报告、Architecture、图形、trace 和脱敏输入输出摘要。真实业务结果从成功运行返回的 Context 或业务入口读取；摘要文件用于审计形状，不是业务返回值。

`delegate-cli` 把 workflow 作为普通业务 CLI 使用。业务 stdout/stderr 不添加 VibeFlow 范围说明，框架诊断写入当次 run 的 `vibeflow.log`。
