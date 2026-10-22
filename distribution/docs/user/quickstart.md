# 快速开始

当前源码使用 **Workflow ABI v10**。从旧版本升级时，重新构建 AOT；原生 `definition_id:"vibeflow.io"` / `io` 配置须迁移为普通 SDK 端口节点。命名入口、调用授权与跨 workflow 通信见[多入口与通信](workflow-coordination.md)。

项目至少注册一个独立子目录 root，不能使用无 root 或同目录模式。当前 AOT v4、预览快照 v4；旧配置与产物需重新构建/生成，不提供读取兼容。布局、共享资源和治理选择见[项目治理](project-governance.md)。

默认审查交付[离线 HTML 预览](local-preview.md)，SVG 使用 `review --with-svg` 按需生成。AOT 执行不生成预览报告。

发行包包含两个最小可运行项目：`python_project` 使用 Python Runtime，`javascript_project` 使用 JavaScript/TypeScript AOT。每个项目都采用 start、输入边界、一个业务处理 Node、输出边界和 end 的结构。

解压后可直接双击根目录 `vibeflow-preview.html` 打开离线浏览工具，初始历史为空。
运行 `review` 生成快照后，在页面刷新历史或使用命令返回的快照定位链接查看对应 workflow。

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
python run.py quality-check --workspace vibeflow_config.jsonc
```

业务 Node 和独立 BaseLib 从标准目录发现，Rule 与 NodeType 由 Plugin 提供；均使用 Python SDK 声明，见 [Python 开发](python-development.md)。最小项目的固定插件在 `python_project/plugins/code_plugin/plugin.py`，由 workflow 的 `plugins` 选择。

## JavaScript 最短路径

业务代码位置标在 `javascript_project/nodes/process_payload.ts`。首次使用先安装锁定依赖：

```bash
npm ci --prefix javascript_project
python run.py architecture --config javascript_project/configs/main.jsonc --output javascript_project/ARCHITECTURE.jsonc
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

Node、DataSchema 和生成入口见 [JavaScript/TypeScript 开发](javascript-development.md)。最小项目的固定插件在 `javascript_project/plugins/code_plugin/plugin.ts`，资源使用 `@vibeflow/plugin` 声明。

## 按任务继续阅读

| 任务 | 文档 |
| --- | --- |
| 修改 pipeline、edge、输入输出 | [Workflow 与 Config](workflow-and-config.md) |
| 开发 Python Node 或 BaseLib | [Python 开发](python-development.md) |
| 开发 JS/TS Node 或 AOT 入口 | [JavaScript 开发](javascript-development.md) |
| 开发 Nodeset 或 Loop | [Nodeset 与 Loop](nodeset-types-and-loops.md) |
| 编写 Rule、组合 Ruleset 或选择检查约束 | [Rule 与 Node](rules-and-nodes.md) |
| 开发 Plugin 或宿主能力 | [Plugin 与集成](plugins-and-integrations.md) |
| 拆分实现文件、设置样式或查看资源依赖 | [多文件资源](multifile-resources.md) |
| 选择命令或解释结果 | [命令与检查范围](commands-and-results.md) |
