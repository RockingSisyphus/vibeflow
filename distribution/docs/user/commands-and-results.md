# 命令、产物与检查范围

VibeFlow 的公开命令分别报告结构、质量、构建、审核产物或执行证据。JSON 保留 `status`，并提供 `result_code`、`validation_scope`、`summary`、`checked` 和 `not_checked`。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 更新 Architecture | `python run.py architecture --config <config> --output <root>/ARCHITECTURE.jsonc` |
| 检查 Architecture 新鲜度 | 在上述命令后添加 `--check` |
| 静态结构检查 | `python run.py validate --config <config>` |
| 项目质量检查 | `python run.py quality --path <root>` |
| 本地审核预览 | `python run.py review --config <config>` |
| 可选 SVG 对照 | `python run.py review --config <config> --output reports/workflow.svg` |
| 重建预览索引 | `python run.py preview --reindex` |
| 查看有效规则图 | `python run.py review-rules --config <config> --json` |
| 查询当前资源与来源 | `python run.py inspect-resources --config <config> --json` |
| Python 执行 | `python run.py run --config <config> --input <input.json>` |
| Python AOT | `python run.py build --config <config> --out-dir <dir>`，再以 `python <dir>/run.py run --input <input.json>` 运行 |
| JavaScript AOT | `python run.py build --config <config> --target node --profile esm-module --out-dir <dir>` |
| 内核完整性 | `python run.py verify-kernel` |

`review` 生成并校验审核产物。collaborative profile 中，产物成功仍需后续人工批准；autonomous profile 按任务直接完成适用门禁。

对实际 Config 的完整工作流执行 `review`，得到根目录的离线 HTML 预览和历史快照，并更新已登记的 `ARCHITECTURE.jsonc`。审核时交付 `preview` 完整路径、`preview_id` 与 `#snapshot=<preview_id>&view=flow` 定位链接，让用户查看当次 workflow。默认不调用 Mermaid；使用 `--with-svg` 添加对照附件，显式指定 `--output` 时另交付原有展开 SVG。JSONC 保存声明、入口与支撑文件、真实依赖、有效规则和展示来源。多文件图形内容见[图形与 Architecture](multifile-resources.md#审查与交付)，页面交互和目录见[本地预览与历史](local-preview.md)。

可选 SVG 展开图的资源目录按 `plugins`、`base_lib` 排列：目录父节点连接当前配置使用的资源。Node 显示在流程的实际调用位置；Nodeset 按定义的 `expand` 设置展开。`export-svg --expand-nodesets` 和 `export-mermaid --mermaid-layout review-columns` 沿用这一展示方式。有效规则与参数来源通过 `review-rules --json` 查询。

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

`quality-check` 检查项目、全部已注册 root 及现存 workflow。`--path` 用于定位所属项目，指定某个 root 或源码文件也会完成项目级检查。JSON 包含顶层 `errors`、`warnings`、逐 workflow 的 `reports`、治理 `governance` 和 `project_architecture`；警告为 `CONCERNS`、退出码 0，错误为 `FAIL` 或 `ERROR`、退出码 1。

项目必须有 `vibeflow_config.jsonc`，至少注册一个独立子目录 root；各 root 用 `vibeflow_project.jsonc` 声明 Target。项目和 root 的可选规则及参数分别写入 `project_rules.jsonc`、`root_rules.jsonc`。显式 `[]` 只取消本层可选规则，不能跳过 workflow 检查或加载契约。质量检查不再提供独立源码扫描、`--exclude-dir`、`--exclude-path` 或全局阈值开关；目录用途和源码质量限制通过对应 Rule 参数配置，详见[项目治理](project-governance.md)。

单 workflow 的构建和源码运行检查所属 root、当前 workflow 与所用资源；共享资源从项目层解析，不能直接引用其他 root 的私有资源。AOT 执行不扫描项目、不审图、不生成预览。发行包装器自动使用同级项目配置，直接调用内核可显式指定 `--workspace`。

## 工作流执行探针

执行探针与静态 validate 分开运行。它只在有证据时报告：

- 工作流成功启动；
- Node 按编译计划执行；
- 声明的最终输出已经产生；
- 执行中没有结构性错误。

Python 源码及 bundle 的 `run` 都在 run 目录写入 `workflow_execution_report.json`。JavaScript 最小项目先完成 AOT build，再导入生成入口并由 `scripts/workflow_execution_probe.mjs` 生成同形报告。

## 运行产物

Python run 目录包含健康报告、编译图事实、trace 和脱敏输入输出摘要；`preview.json` 指向集中存放 Architecture 数据及可选 SVG 附件的预览快照。真实业务结果从成功运行返回值或业务入口读取；摘要文件用于审计形状，不是业务返回值。预览失败的具体原因写入 `preview.error.txt`，不阻止业务执行。

`delegate-cli` 把 workflow 作为普通业务 CLI 使用。业务 stdout/stderr 不添加 VibeFlow 范围说明，框架诊断写入当次 run 的 `vibeflow.log`。
