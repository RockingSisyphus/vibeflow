# 快速开始

发行包包含两个最小可运行项目：`python_project` 使用 Python Runtime，`javascript_project` 使用 JavaScript/TypeScript AOT。每个项目都采用 start、输入边界、一个业务处理 Node、输出边界和 end 的结构。

## 选择项目根

任务涉及 Python Node、Registry 或直接运行 workflow 时，修改 `python_project/`。任务涉及 JavaScript/TypeScript descriptor 或构建普通 ESM 时，修改 `javascript_project/`。一次 workflow 只属于一个 Target。

开始修改前依次阅读：

1. 根目录 `AGENTS.md`；
2. 所选 root 的 README 和 `vibeflow_project.jsonc`；
3. 已登记的 `ARCHITECTURE.jsonc`；
4. 架构文档所指向的真实 Config、Nodeset 和 Node source；
5. 与任务对应的使用者文档。

Architecture 是生成的审查视图。结构变更落在真实 source 中，然后重新生成 Architecture。

## Python 最短路径

业务代码位置标在 `python_project/nodes/workflow_nodes.py`。修改后执行：

```bash
python run.py architecture --config python_project/configs/main.jsonc --output python_project/ARCHITECTURE.jsonc
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
python run.py quality --path python_project
```

Node、Registry 和 BaseLib 接口见 [Python 开发](python-development.md)。

## JavaScript 最短路径

业务代码位置标在 `javascript_project/nodes/process_payload.ts`。首次使用先安装锁定依赖：

```bash
npm ci --prefix javascript_project
python run.py architecture --config javascript_project/configs/main.jsonc --output javascript_project/ARCHITECTURE.jsonc
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

Descriptor、Data Schema 和生成入口见 [JavaScript/TypeScript 开发](javascript-development.md)。

## 按任务继续阅读

| 任务 | 文档 |
| --- | --- |
| 修改 pipeline、edge、输入输出 | [Workflow 与 Config](workflow-and-config.md) |
| 开发 Python Node 或 BaseLib | [Python 开发](python-development.md) |
| 开发 JS/TS Node 或 AOT 入口 | [JavaScript 开发](javascript-development.md) |
| 开发 Nodeset 或 Loop | [Nodeset 与 Loop](nodesets-and-loops.md) |
| 开发 Plugin 或宿主能力 | [Plugin 与集成](plugins-and-integrations.md) |
| 选择命令或解释结果 | [命令与检查范围](commands-and-results.md) |
