# 命令、产物与检查范围

VibeFlow 命令分别生成结构、质量、构建、审核或执行结果。JSON 的 `status`、`result_code`、`validation_scope`、`summary`、`checked` 和 `not_checked` 描述本次操作及其证据范围。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 静态结构检查 | `python run.py validate --config <config>` |
| 项目质量检查 | `python run.py quality --path <root>` |
| 本地审核预览 | `python run.py review --config <config>` |
| 重建预览索引 | `python run.py preview --reindex` |
| 查看有效规则图 | `python run.py review-rules --config <config> --json` |
| 查询当前资源与来源 | `python run.py inspect-resources --config <config> --json` |
| Python 执行 | `python run.py run --config <config> --input <input.json>` |
| Python AOT | `python run.py build --config <config> --out-dir <dir>`，再用 `python <dir>/run.py run --input <input.json>` 运行 |
| JavaScript AOT | `python run.py build --config <config> --target node --profile esm-module --out-dir <dir>` |
| 内核完整性 | `python run.py verify-kernel` |

发行包装器自动使用同级项目配置；直接调用内核时可显式指定 `--workspace`。

## 结果判读

`checked` 列出实际完成的检查，`not_checked` 说明本次覆盖以外的内容。结构检查包括配置登记、契约形状、数据可达性、控制流、副作用约束及实际执行的治理检查。quality、build 和 review 增加各自完成的阶段。

| 证据 | 支持的结论 |
| --- | --- |
| `validate` / `quality-check` | 实际检查范围内的结构、源码健康度及所选领域约束 |
| `build` | 指定 Target 的产物已生成 |
| 工作流执行探针 | 指定输入的实际执行路径及声明输出 |
| 项目测试 | 业务结果正确性、需求符合性及领域数据约定 |
| 真实环境验收 | 实际宿主与外部接口行为 |

按本次源码与输入报告相应结果。检查失败时，根据诊断修复源码、配置或输入，再执行相关检查。

## 项目质量检查

`quality-check` 检查项目、全部已注册 root 及现存 workflow；`--path` 定位所属项目。JSON 包含 `errors`、`warnings`、逐 workflow 的 `reports`、治理 `governance` 和 `project_architecture`。警告产生 `CONCERNS`、退出码 0；错误产生 `FAIL` 或 `ERROR`、退出码 1。

单 workflow 构建和源码运行检查所属 root、当前 workflow、使用的资源及适用项目规则。完整项目检查负责共享资源引用统计。AOT 执行使用已准备的计划与实现。检查政策和参数见[项目治理](project-governance.md)。

## 工作流执行探针

探针通过实际运行取得四项证据：成功启动、Node 按计划执行、最终声明输出产生、执行过程满足结构约定。

Python 源码及 bundle 的 `run` 在 run 目录写入 `workflow_execution_report.json`。JavaScript 最小项目先 build，再由 `scripts/workflow_execution_probe.mjs` 导入生成入口并写出同形报告。

## 运行产物

Python run 目录保存健康报告、编译图事实、trace 和脱敏输入输出摘要。真实业务结果从成功运行的返回值或业务入口读取，摘要用于检查数据形状。`preview.json` 定位集中保存的预览快照；预览错误写入 `preview.error.txt`。

`delegate-cli` 将 workflow 作为业务 CLI 使用，保留业务标准流与退出码，框架诊断写入当次 `vibeflow.log`。

## 相关文档

- [架构阅读与维护](architecture.md)：架构文档的生成、登记与检查命令。
- [本地预览](local-preview.md)：HTML 审核材料与快照交付。
- [运行观测](runtime-observation.md)：日志文件、状态与业务进度。
- [产品检查边界](product-check-boundaries.md)：源码分析覆盖与局限。
