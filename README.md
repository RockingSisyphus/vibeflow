# VibeFlow

[English](README.en.md)

VibeFlow 把 AI 参与开发的程序组织成可执行、可检查、可生成架构视图的显式流程图。业务逻辑位于小型 Node 中，Config 声明控制流，端口契约声明数据流，Core 在运行或构建前验证结构。

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

![VibeFlow comprehensive flowchart](docs/assets/comprehensive_flowchart.svg)

## 主要能力

- Python Runtime、Python 目录 AOT 与 JavaScript/TypeScript AOT；
- Python 和 JS/TS 插件 SDK，以代码声明 Node、Rule、Ruleset 等资源，由 workflow 显式选择；
- 可组合的 Rule/Ruleset，以及 Node、Nodeset、Loop、Capability 与显式副作用边界；
- Node、BaseLib、Plugin 与 Host 的多文件实现、源码归属、逐文件审查和默认图形样式；
- 确定性 Architecture JSONC、Mermaid、ASCII、展开 SVG，以及[离线预览与历史时间线](distribution/docs/user/local-preview.md)；
- 配置、契约、可达性、控制流、质量、构建与执行证据检查；
- collaborative 与 autonomous 两种开发协议，共享同一 Core 和机器规则。

VibeFlow 检查工程结构、源码健康度和所选领域约束；项目测试与真实环境验收验证业务结果及外部接口行为。

## 开始使用

从 GitHub Release 下载所需发行包并解压：

- `vibeflow-distribution-<version>.zip`：人机协同审核；
- `vibeflow-distribution-autonomous-<version>.zip`：无人值守开发。

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

- [项目概览](distribution/docs/overview.md)
- [使用者开发文档](docs/README.md#使用者开发)
- [多文件资源与展示](distribution/docs/user/multifile-resources.md)
- [系统设计](docs/README.md#系统设计)
- [内核维护](docs/README.md#内核维护)

源码仓库完整门禁：

```bash
python tools/verify_project.py --full
```

当前发行包版本为 `1.1.5`，Workflow ABI 为 `vibeflow.workflow.v8`，AOT manifest 为 `vibeflow.aot-build.v3`。两个分发包均预装根目录 HTML 入口、配置、离线资源和空历史索引，解压即可打开，无需先运行命令；运行 review 后查看对应快照。SVG 仍为可选对照，无业务配置或快照格式迁移。展开 Nodeset / Loop 时隐藏原卡片，名称与说明显示在分组顶部。Python AOT 固定描述和插件绑定索引按 Bundle 复用，已有 AOT 产物需重新构建以带入修复。完整变更见[1.1.5 构建说明](docs/maintainers/history/release-1.1.5.md)。

质量检查只覆盖当前实际选择的 Rule；不证明业务正确、代码安全、算法确定性或全部无副作用。有限 Python 输入写入规则独立于效果政策，详见[产品检查边界](distribution/docs/user/product-check-boundaries.md)。

## 仓库目录用途

根目录仅保存项目入口、许可证和构建 / Git 元数据。开发文档归 docs，用户文档原稿与发行资源归 distribution；临时脚本和执行产物不能堆在根目录。

| 目录 | 用途 |
| --- | --- |
| [src](src/README.md) | 产品各模块的核心源码与运行资源 |
| [tests](tests/README.md) | 非沙盒的功能、代码和集成回归 |
| [sandbox](sandbox/README.md) | Python / JavaScript 真实使用项目，加载工作区 src |
| [repo_check](repo_check/README.md) | 独立的仓库内部质检工具 |
| [tools](tools/README.md) | 开发、验证、清理和辅助工具 |
| [distribution](distribution/README.md) | 发行构建器、模板、提示词和用户文档原稿 |
| [dist](dist/README.md) | 最新正式发行目录、ZIP 和校验清单 |
| [archive](archive/README.md) | 被替换的历史正式发行包 |
| [docs](docs/README.md) | 设计、维护、历史结论和正文附件 |
| [references](references/README.md) | 外来参考项目 |
| [.github](.github/DIRECTORY.md) | GitHub CI 与协作模板 |

新建自行维护的子目录时同步写明职责。过时且不再使用的文件直接删除；运行产物在仓库外临时工作区使用并及时清理。详细规则见[仓库目录职责](docs/maintainers/directory-layout.md)。

当前工作树另在实施未发布的[命名入口与独立 Workflow 通信](distribution/docs/user/workflow-coordination.md)：源码使用 Workflow ABI v9，旧 AOT 需重建，原生 IO 配置需迁移；既有 1.1.5 构建记录仍保留原 ABI 信息。功能的实施与验收证据见[维护记录](docs/maintainers/workflow-communication.md)。本轮不自动发布新版本。
