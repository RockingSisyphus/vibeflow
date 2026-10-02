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

正式审核必须对真实 Config 的完整工作流执行 `review`。工具生成成功不能证明配置就是实际生产流程；局部、概念性或脱离真实调用的配置不能凭 PASS 作为批准依据。协同模式对原位 planned 变更及新增工作流的具体要求见其 profile 文档。

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

报告完成状态时，按本次任务实际执行的证据区分：`validate`／`quality-check` 说明其 `checked` 范围内的静态结果；`build` 说明目标产物已构建；执行探针说明指定输入走过的执行路径；业务测试和真实环境验收才支持相应的业务结论。局部 PASS、产物存在或旧报告不能代替当前代码对应的顶层结果。任务要求的检查失败时，先读失败项并修复原因；代码和输入未变化时，无需反复运行同一失败检查。

### Python 与 JavaScript 项目质量

`quality-check` 检查当前根的手写源码与找到的工作流；即使没有工作流，也会输出 `source_quality`。JSON 同时包含 `source_quality`、逐工作流的 `reports` 和顶层状态；Python 原有的源码报告字段仍保留在顶层。警告产生 `CONCERNS`、退出码 0，错误产生 `FAIL`、退出码 1。

在已选择的 workspace 中，`quality --path <root>` 只扫描该 root 的源码与工作流。Python 工作流依赖解析保留完整 workspace 的声明与规则资源，支持兄弟 root 的 BaseLib 与 Node。发行包装器会自动选用同目录的 `vibeflow_config.jsonc`；直接调用内核 CLI 时用 `--workspace` 指定。没有 workspace 的独立项目仍按自身 `vibeflow_project.jsonc` 加载。

JavaScript/TypeScript 扫描 `.js`、`.jsx`、`.ts`、`.tsx`、`.mjs`、`.cjs`、`.mts`、`.cts` 及声明源码，包括未注册的手写文件和测试文件；自动排除 `generated`、`dist`、`build`、`node_modules` 等产物目录。可重复使用 `--exclude-dir NAME` 和 `--exclude-path ROOT_RELATIVE_PATH` 排除其他目录或文件。独立 `--path` 源码扫描需要项目本地安装的 TypeScript；`--enable-structure-limits` 可为独立扫描启用根目录结构上限。

Node/helper 的源码大小、复杂度和依赖链由所选 Ruleset 中的规则检查。默认依赖链包含 Node 本身，长度超过 4 为警告、超过 6 为错误；仅计入可解析的项目内导入。现有 `policy` 数值配置作为内置 Rule 的默认参数，显式规则参数和覆盖关系优先；旧 `policy.rules` 豁免和降级改为规则组合及覆盖。`validate`、`review`、`build` 执行当前范围的静态入口；`run` 只执行运行入口，新增领域规则默认进入静态入口。`review-rules --config CONFIG --node CALL_PATH` 可查看该调用的有效规则及参数来源，生成 JSON、Mermaid 或 SVG，过程不加载业务实现。规则接口与迁移示例见 [规则与分类](rules-and-categories.md)。

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
