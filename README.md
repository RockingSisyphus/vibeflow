# VibeFlow

[English](README.en.md)

VibeFlow 把 AI 参与开发的程序组织成可执行、可检查、可生成架构视图的显式流程图。业务逻辑位于小型 Node 中，Config 声明控制流，端口契约声明数据流，Core 在运行或构建前验证结构。

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

![VibeFlow comprehensive flowchart](docs/assets/comprehensive_flowchart.svg)

## 主要能力

- Python Runtime 与 JavaScript/TypeScript AOT；
- Python 和 JS/TS 插件 SDK，以代码声明 Node、Rule、Ruleset 等资源，由 workflow 显式选择；
- 可组合的 Rule/Ruleset，以及 Node、Nodeset、Loop、Capability 与显式副作用边界；
- Node、BaseLib、Plugin 与 Host 的多文件实现、源码归属、逐文件审查和默认图形样式；
- 确定性 Architecture JSONC、Mermaid、ASCII 和包含资源依赖的展开 SVG；
- 配置、契约、可达性、控制流、质量、构建与执行证据检查；
- collaborative 与 autonomous 两种开发协议，共享同一 Core 和机器规则。

VibeFlow 检查工程结构、源码健康度和所选领域约束；项目测试与真实环境验收验证业务结果及外部接口行为。

## 开始使用

从 GitHub Release 下载所需发行包并解压：

- `vibeflow-distribution-0.15.0.zip`：人机协同审核；
- `vibeflow-distribution-autonomous-0.15.0.zip`：无人值守开发。

打开解压目录后，AI 从根 `AGENTS.md` 获得任务阅读路径；人类从 `kernel/docs/README.md` 进入使用者手册。两个包都包含最小的 `python_project/` 和 `javascript_project/`。

Python 最短验证：

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
```

JavaScript 最短验证：

```bash
npm ci --prefix javascript_project
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

## 文档

- [项目概览](docs/overview.md)
- [使用者开发文档](docs/README.md#使用者开发)
- [多文件资源与展示](docs/user/multifile-resources.md)
- [系统设计](docs/README.md#系统设计)
- [内核维护](docs/README.md#内核维护)

源码仓库完整门禁：

```bash
python tools/verify_project.py --full
```

当前包版本为 `0.15.0`，Workflow ABI 为 `vibeflow.workflow.v4`。
