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
| 查看有效规则图 | `python run.py review-rules --config <config> --json` |
| 查询当前资源与来源 | `python run.py inspect-resources --config <config> --json` |
| Python 执行 | `python run.py run --config <config> --input <input.json>` |
| JavaScript AOT | `python run.py build --config <config> --target node --profile esm-module --out-dir <dir>` |
| 内核完整性 | `python run.py verify-kernel` |

`review` 生成并校验审核产物。collaborative profile 中，产物成功仍需后续人工批准；autonomous profile 按任务直接完成适用门禁。

对实际 Config 的完整工作流执行 `review`，得到一张展开 SVG，并更新已登记的 `ARCHITECTURE.jsonc`。SVG 展示工作流与资源区，JSONC 保存声明、入口与支撑文件、真实依赖、有效规则和展示来源。审核失败时保留已有正式产物。多文件图形内容见[图形与 Architecture](multifile-resources.md#图形与-architecture)。

展开图的资源目录按 `plugins`、`base_lib`、`host_extensions` 排列：目录父节点连接当前配置使用的资源。Node 显示在流程的实际调用位置；Nodeset 按定义的 `expand` 设置展开。`export-svg --expand-nodesets` 和 `export-mermaid --mermaid-layout review-columns` 沿用这一展示方式。有效规则与参数来源通过 `review-rules --json` 查询。

## 运行日志与监控

Python 执行和 Node.js AOT 调用生成 `vibeflow.log`、`business.log` 和 `status.json`。通过状态文件读取启动、运行、成功或失败状态；Node 可更新缓存中的业务信息。固定路径、更新间隔和双语言 API 见[运行日志与状态接口](runtime-observation.md)。

## 检查范围

一次命令的 `checked` 只列出实际完成的阶段。结构检查可以覆盖：

- 配置和登记关系；
- Node 契约形状；
- 数据可达性；
- 控制流；
- 副作用边界；
- 实际执行的项目结构检查。

quality、build 和 review 会增加各自实际完成的检查。失败或无法取得证据的阶段不会写入 `checked`。

按本次源码和输入报告各层证据：

| 证据 | 可以报告的结果 |
| --- | --- |
| `validate` / `quality-check` | `checked` 范围内的结构、源码健康度及所选领域约束 |
| `build` | 指定 Target 的产物已生成 |
| 工作流执行探针 | 指定输入的实际执行路径及声明输出 |
| 项目测试 | 业务结果正确性、需求符合性及领域数据约定 |
| 真实环境验收 | 实际宿主与外部接口行为 |

检查失败时，依据当次诊断修复源码、配置或输入，再重新执行相关检查。

### Python 与 JavaScript 项目质量

`quality-check` 检查当前根的手写源码与找到的工作流；即使没有工作流，也会输出 `source_quality`。JSON 同时包含 `source_quality`、逐工作流的 `reports` 和顶层状态；Python 原有的源码报告字段仍保留在顶层。警告产生 `CONCERNS`、退出码 0，错误产生 `FAIL`、退出码 1。

在已选择的 workspace 中，`quality --path <root>` 只扫描该 root 的源码与工作流。依赖定位保留完整 workspace 的 root 解析上下文，资源来自当前 workflow 选中的插件；兄弟 root 的 BaseLib 与 Node 通过显式插件 source 和 root 接入。发行包装器会自动选用同目录的 `vibeflow_config.jsonc`；直接调用内核 CLI 时用 `--workspace` 指定。没有 workspace 的独立项目仍按自身 `vibeflow_project.jsonc` 加载。

JavaScript/TypeScript 扫描 `.js`、`.jsx`、`.ts`、`.tsx`、`.mjs`、`.cjs`、`.mts`、`.cts` 及声明源码，包括未注册的手写文件和测试文件；自动排除 `generated`、`dist`、`build`、`node_modules` 等产物目录。可重复使用 `--exclude-dir NAME` 和 `--exclude-path ROOT_RELATIVE_PATH` 排除其他目录或文件。独立 `--path` 源码扫描需要项目本地安装的 TypeScript；`--enable-structure-limits` 可为独立扫描启用根目录结构上限。

Node、BaseLib、Plugin 和 Host 的入口与支撑文件由各自所选 Ruleset 检查。默认可维护性规则逐文件检查 500 行上限；默认依赖链包含入口本身，长度超过 4 为警告、超过 6 为错误，仅计入可解析的项目内导入。`policy` 数值配置提供内置 Rule 的默认参数，显式规则参数和覆盖关系优先。参数组合见[Rule 与 Node](rules-and-nodes.md#ruleset-与局部覆盖)，旧写法调整见[声明迁移](rule-system-migration.md)。

`validate`、`review`、`build` 执行当前范围的静态入口；Python `run` 执行运行入口，新增领域规则默认进入静态入口。`review-rules --config CONFIG --node CALL_PATH` 展示该调用的有效规则及参数来源，支持 JSON、Mermaid 或 SVG。查询和预览的加载顺序见[加载与检查](plugins-and-integrations.md#加载与检查)。

## 工作流执行探针

执行探针与静态 validate 分开运行。它只在有证据时报告：

- 工作流成功启动；
- Node 按编译计划执行；
- 声明的最终输出已经产生；
- 执行中没有结构性错误。

Python `run` 会在 run 目录写入 `workflow_execution_report.json`。JavaScript 最小项目先完成 AOT build，再导入生成入口并由 `scripts/workflow_execution_probe.mjs` 生成同形报告。

## 运行产物

Python run 目录包含健康报告、Architecture、图形、trace 和脱敏输入输出摘要。真实业务结果从成功运行返回值或业务入口读取；摘要文件用于审计形状，不是业务返回值。

`delegate-cli` 把 workflow 作为普通业务 CLI 使用。业务 stdout/stderr 不添加 VibeFlow 范围说明，框架诊断写入当次 run 的 `vibeflow.log`。
