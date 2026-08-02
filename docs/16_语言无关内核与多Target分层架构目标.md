# VibeFlow 语言无关内核与多 Target 分层架构

> 状态：VibeFlow 0.9.0 使用下文的分层导入路径，并以静态依赖门禁保证两个 Target 及其 Application closure 完全隔离。

## 编译链

VibeFlow 只定义一次工作流语义，再由 Target 绑定具体实现：

```text
项目文件
→ Tooling 加载
→ Core 审核为 ValidatedWorkflow
→ Block Compiler 生成 WorkflowPlan（包含 BlockPlan）
→ Target BindingPlan 绑定实现
→ Python Runtime 或 JavaScript emitter
```

这条链共享 workflow、contract、route、nodeset、loop、TaskPlan、Capability 和错误语义。Python、JavaScript 以及未来语言的实现和工具链相互隔离。

## 目录与职责

```text
src/vibeflow/
├── core/
│   ├── config/             # 语言无关配置模型与校验
│   ├── descriptors/        # 通用资源描述
│   ├── quality/            # 纯内存质量判定
│   └── inspection/         # 中立架构快照
├── block_compiler/          # ValidatedWorkflow → WorkflowPlan
├── targets/
│   ├── python/
│   │   ├── project/         # Node、base_lib、Plugin、Registry 与绑定
│   │   ├── quality/         # Python AST、纯度与实现事实
│   │   └── runtime/         # Python 执行器
│   └── javascript/
│       ├── frontend/       # JS/TS descriptor、类型与绑定
│       ├── quality/        # completion、Promise 与 import 审计
│       ├── build/          # emitter、Node 工具链与发布
│       └── resources/      # AOT 构建资源
└── tooling/
    ├── application/
    │   ├── python/      # Python CLI、runner、project 与 presentation
    │   └── javascript/  # JavaScript AOT 工程编排与 CLI
    ├── project/             # JSONC、workspace、路径与文件加载
    └── __init__.py          # 不引入 Target 的轻量命名空间
```

正式 Target 名是 `javascript`；TypeScript 是该 Target 支持的实现语言。

## Core

Core 的纯内存入口是：

```python
from vibeflow.core import CoreCompileRequest, compile_core

compilation = compile_core(CoreCompileRequest(...))
```

Core 负责公共流程模型、输入输出契约、图算法、结构健康检查和通用 descriptor 规则。它不接收路径、AST、源码、callable、class、插件实例或宿主对象，也不读取文件、环境或启动进程。

Core Quality 同样只处理普通事实：

```python
from vibeflow.core.quality import (
    ProjectQualityFacts,
    QualityPolicy,
    evaluate_project_quality,
)

report = evaluate_project_quality(ProjectQualityFacts(...), QualityPolicy(...))
```

## Block Compiler

```python
from vibeflow.block_compiler import compile_workflow

plan = compile_workflow(validated_workflow, implementation_facts)
```

Block Compiler 生成冻结、确定、可序列化的 `WorkflowPlan`、`BlockPlan`、`NodeCallPlan`、`RoutePlan`、`ConditionPlan` 和 `TaskPlan`。计划只包含普通数据，不保存 Target 实现、插件实例或生成源码。相同输入必须得到字节一致的计划 JSON。

## Target

Python Target 的稳定入口按职责划分：

```python
from vibeflow.targets.python.project import NodeInfo, NodeRegistry, PluginInfo
from vibeflow.targets.python.quality import validate_graph_health
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
```

`PythonBindingPlan` 保存 callable、有效参数、插件引用和源码位置。Python Runtime 支持 plan、block、compiled、线程任务、`result_key`、detached、永久 loop 和 Port。

JavaScript Target 的稳定入口按 frontend、quality 和 build 划分：

```python
from vibeflow.targets.javascript.frontend import build_javascript_binding_plan
from vibeflow.targets.javascript.quality import validate_javascript_quality
from vibeflow.targets.javascript.build import BuildRequest, build_aot
```

`JavascriptBindingPlan` 保存 JS/TS 源码、Schema、base_lib、Capability、Plugin、Host Extension 和 import policy。Emitter 使用 `WorkflowPlan + JavascriptBindingPlan` 生成 `vibeflow.workflow.v2` ESM；JS/TS Plugin 使用 `vibeflow.plugin.v1`。

两个 Target 不能直接或经 Tooling 间接导入。Python Application closure 只能到达 Python Target，JavaScript Application closure 只能到达 JavaScript Target；中立 Tooling 不依赖任一 Target。

## Tooling

Tooling 只处理外部接线和表现层：

- `tooling.project` 读取 JSONC、workspace、descriptor 和路径；
- `tooling.application.python` 编排 Python Target，并拥有 Python 项目扫描、CLI、runner 和 architecture presentation；
- `tooling.application.javascript` 编排 JavaScript Target 的 AOT 工程与 CLI；
- `tooling.project` 是两个 Application 可共享的中立文件接线，不引入任一 Target。

用户项目质量检查是 Core 能力，文件接线遵循分层链路：

```text
Tooling 扫描文件和 workspace
→ Python/JavaScript Target 提取语言事实
→ Core Quality 判定、去重并应用 policy
→ Tooling 输出 text/JSON 和退出码
```

用户入口保持为 `python -m vibeflow quality-check`。这是 VibeFlow 内置能力，与根目录独立仓库自检器 `quality/` 不同。

## 依赖规则

```text
tooling ──────────────────────────────┐
  ├─→ targets/python ──────┐          │
  ├─→ targets/javascript ───├─→ block_compiler → core
  └──────────────────────────────┘
```

- Core 不依赖 Block Compiler、Target 或 Tooling；
- Block Compiler 只依赖 Core；
- Target 只依赖自身、Block Compiler 和 Core；
- Target-specific Application 只能编排自己的 Target；其他 Tooling 保持 Target-neutral，底层不得反向依赖 Tooling；
- Python 与 JavaScript 的 Application dependency closure 不得相交；
- JavaScript `frontend/quality` 不启动 subprocess，`build` 才能调用 Node 工具链；
- Python `quality` 不遍历文件，`project` 才能执行受控动态 import。

0.9 不恢复根级业务导出，也不恢复 `aot`、`runtime`、`portable`、`config`、`health`、`purity`、`devtools`、`rendering`、`workspace` 等旧 API 路径。项目应直接使用所属层的稳定入口。

## Sandbox 与验证

```text
sandbox/
├── python/
│   ├── minimal/
│   └── integration/
└── javascript/
    ├── minimal/
    └── integration/
```

Sandbox 默认把依赖、构建和报告放进临时目录；`--keep-artifacts` 才保留到被忽略的 `.artifacts/`。

完整验证入口是：

```bash
python tools/verify_project.py --full
```

根目录 `quality/` 是不导入 VibeFlow 的独立仓库自检器。可单独运行 `base`、`core`、`block-compiler`、`python-target`、`javascript-target` 或 `all` profile：

```bash
python quality/run.py --profile all
```

工作区清理先预览，再显式应用：

```bash
python tools/clean_workspace.py
python tools/clean_workspace.py --apply
```

清理器只处理明确列出的生成物；`references/`、`distribution/` 源模板和 `.git/` 永不在清理范围内。

## Plugin、Planned 与 Host Extension

Core 用冻结 descriptor 和 selection 统一描述 `policy`、`compiler`、`runtime` 三类 Plugin；各 Target 只绑定自己的实现。JS/TS 实现导出 `createPlugin(context)`，ABI 常量为 `vibeflow.plugin.v1`：Policy/Compiler Plugin 在 AOT 构建期执行检查，Runtime Plugin 在每次 workflow 调用内执行 hook 并释放。它们不能注册长期监听器或提供宿主生命周期。

Host Extension 是 JavaScript Target 的宿主生命周期资源。它由 `createWorkflowHost()` 创建，负责 `start()` / `stop()`、长期事件接线和 Capability provider；它不是 Plugin，也不进入单次 workflow 的 runtime hook 链。

Plugin 与 Host Extension 均可在 workflow 中标为 `planned`。Planned 项只进入架构文档和图形审查，不解析源码、不绑定实现、不执行 hook、不打包，也不提供 Capability。implemented 资源不能依赖 planned 资源。

## 扩展边界

新增语言时实现新的 Target 与专属 Application 接线，复用 Core 与 Block Compiler。Plugin hook 与 Host Extension 生命周期保持分工；通用语义不得复制到某个 Target。
