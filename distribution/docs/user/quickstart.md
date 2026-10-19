# 快速开始

从 1.0.0 及更早版本升级到 1.1.1 的项目须先完成[并发接口迁移](graph-concurrency.md#从旧任务接口迁移)，再重新构建。旧任务管理配置和 ABI v7 产物不能直接交给当前运行器。从 1.0.1 / 1.0.2 升级无需新增业务配置迁移。默认审查交付[离线 HTML 预览](local-preview.md)；旧版预览数据须重新生成，SVG 使用 `review --with-svg` 按需生成。

从 1.1.0 升级无需迁移业务配置或 v2 快照格式。重新执行 `review` 可补齐旧 JavaScript 快照缺失的 Nodeset 计划行为；HTML 工具随命令更新，已有历史与用户数据配置保留。

发行包包含两个最小可运行项目：`python_project` 使用 Python Runtime，`javascript_project` 使用 JavaScript/TypeScript AOT。每个项目都采用 start、输入边界、一个业务处理 Node、输出边界和 end 的结构。

## 选择项目根

先查看工作区的 `vibeflow_config.jsonc`，根据任务选择实际 root 及其声明的 Target。以下 `python_project/` 和 `javascript_project/` 是分发包最小项目的示例路径；业务项目可以有多个不同名称的 root。一次 workflow 只属于一个 Target。

开始修改前依次阅读：

1. 根目录 `AGENTS.md`；
2. 所选 root 的 README 和 `vibeflow_project.jsonc`；
3. 目标目录及其上级目录中更具体的项目 `AGENTS.md`；
4. 已登记的 `ARCHITECTURE.jsonc`；
5. 架构文档所指向的真实 Config、Nodeset、插件声明和资源实现；
6. 与任务对应的使用者文档。

Architecture 是生成的审查视图。结构变更落在真实 source 中，然后重新生成 Architecture。

## Python 最短路径

业务代码位置标在 `python_project/nodes/workflow_nodes.py`。修改后执行：

```bash
python run.py architecture --config python_project/configs/main.jsonc --output python_project/ARCHITECTURE.jsonc
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
python run.py quality --path python_project
```

Node、Rule 和 BaseLib 使用 Python 插件 SDK 声明，见 [Python 开发](python-development.md)。最小项目的固定插件在 `python_project/plugins/code_plugin.py`，由 workflow 的 `plugins` 选择。

## JavaScript 最短路径

业务代码位置标在 `javascript_project/nodes/process_payload.ts`。首次使用先安装锁定依赖：

```bash
npm ci --prefix javascript_project
python run.py architecture --config javascript_project/configs/main.jsonc --output javascript_project/ARCHITECTURE.jsonc
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

Node、DataSchema 和生成入口见 [JavaScript/TypeScript 开发](javascript-development.md)。最小项目的固定插件在 `javascript_project/plugins/code_plugin.ts`，资源使用 `@vibeflow/plugin` 声明。

## 按任务继续阅读

| 任务 | 文档 |
| --- | --- |
| 修改 pipeline、edge、输入输出 | [Workflow 与 Config](workflow-and-config.md) |
| 开发 Python Node 或 BaseLib | [Python 开发](python-development.md) |
| 开发 JS/TS Node 或 AOT 入口 | [JavaScript 开发](javascript-development.md) |
| 开发 Nodeset 或 Loop | [Nodeset 与 Loop](nodesets-and-loops.md) |
| 编写 Rule、组合 Ruleset 或选择检查约束 | [Rule 与 Node](rules-and-nodes.md) |
| 开发 Plugin 或宿主能力 | [Plugin 与集成](plugins-and-integrations.md) |
| 拆分实现文件、设置样式或查看资源依赖 | [多文件资源](multifile-resources.md) |
| 选择命令或解释结果 | [命令与检查范围](commands-and-results.md) |
