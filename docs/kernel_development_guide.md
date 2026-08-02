# VibeFlow 开发者工作流

本文档面向维护 VibeFlow（包名 `vibeflow`）自身的开发者，不是面向业务项目编写 node、nodeset 或 plugin 的使用者指南。

VibeFlow 0.10.0 使用分层 API。根包不导出业务对象，维护代码只使用 `vibeflow.core`、`vibeflow.block_compiler`、`vibeflow.targets.*` 和 `vibeflow.tooling.*` 的所属层入口。

## 基本验证流程

合并或发布前运行统一完整门禁：

```bash
python tools/verify_project.py --full
```

完整门禁依次执行独立仓库自检、各层 pytest、两个 Target 的 Sandbox、Python/JavaScript conformance、Node/browser 与三种 AOT profile、wheel 隔离安装和临时分发包 smoke test。构建和运行产物写入临时目录；进入分发验证前，门禁会通过精确清理器删除自己产生的 cache。它不会覆盖正式分发包。

需要定位分层问题时，直接运行独立自检 profile：

```bash
python quality/run.py --profile base
python quality/run.py --profile core
python quality/run.py --profile block-compiler
python quality/run.py --profile python-target
python quality/run.py --profile javascript-target
python quality/run.py --profile all
```

`quality/` 不进入 wheel，也不导入 VibeFlow。它检查仓库目录、生成物、层间依赖、Core 纯度、Target 隔离和 JavaScript 资源。`python -m vibeflow quality-check` 则是用户项目检查入口，两者职责不同。

## 分层与公共计划维护边界

依赖方向是：

```text
tooling → targets/python ──────┐
        → targets/javascript ─┴→ block_compiler → core
```

标准编译链是：

```text
Tooling 标准化项目数据
→ compile_core(CoreCompileRequest)
→ CoreCompilation / ValidatedWorkflow
→ compile_workflow(ValidatedWorkflow, ImplementationFacts)
→ WorkflowPlan（包含 BlockPlan）
→ PythonBindingPlan 或 JavascriptBindingPlan
→ Python Runtime 或 JavaScript emitter
```

维护规则：

- `WorkflowPlan` / `BlockPlan` 只保存冻结的 JSON 值、稳定 ID、契约、路由、block 引用和 `SourceRef`，不得保存 Python class、callable、实例或生成后的 Python/JavaScript 源码。
- `PythonBindingPlan` 保存 callable、有效参数和插件引用；`JavascriptBindingPlan` 保存 JS/TS 源码、Schema、base_lib、Plugin、Capability、Host Extension 和 import policy。两者都不能进入公共 IR。
- Python Runtime 支持 `ExecutionPlan` 与 plan/block/compiled 三种模式；这些对象属于 Python Target，不进入公共 IR。
- JavaScript emitter 以 `WorkflowPlan + JavascriptBindingPlan` 为语义来源。
- Core 和 Block Compiler 不得做文件、环境、动态 import、subprocess 或语言实现操作；两个 Target 不得互相 import。
- node、`base_lib`、data schema、Capability、Plugin 和 Host Extension 使用静态 JSONC descriptor 建模。静态 descriptor 与 Python 注册同时存在时必须一致。
- JavaScript emitter 根据 `entry_mode` 输出同步 `runWorkflow()` 或异步 `runWorkflowAsync()`，不是把原始流程图或通用 graph walker 搬进目标环境。生成模块被 import 时不得执行业务 workflow 或启动扩展。
- Capability descriptor 只定义依赖契约。实现由宿主在每次调用时注入或由 Host Extension 提供；调用状态、trace、任务和 Capability wrapper 不得保存在可变模块级业务状态中。
- `descriptors.host_extensions` 登记 project 可用扩展，workflow 顶层
  `host_extensions` 选择本流程实际使用的资源。implemented 扩展解析、检查并
  打包；planned 扩展只进入 Architecture JSON 和图形审查，不参与生命周期或
  Capability 提供。
- Plugin 的 Core descriptor/selection 是普通冻结数据。Python 与 JavaScript Target 分别绑定实现；JS/TS 使用 `vibeflow.plugin.v1` 的 `createPlugin(context)`。Policy/Compiler Plugin 在构建期运行，Runtime Plugin 按 invocation 创建和释放，Host Extension 按 host 生命周期 start/stop。三者不得互相代替。
- Planned Plugin 与 Planned Host Extension 只进入审查，不加载源码、不绑定实现、不执行或打包；implemented 资源不能依赖 planned 资源。
- `completion`、`schedule`、`executor` 必须分开建模；同步 JS 计划不得包含 suspend/deferred/detached。TypeScript 源码审计负责拒绝声明不实和未归属 Promise，不增加运行时 thenable 兜底。
- `max_iterations: null`、组合 stop 和无 stop 永久 loop 是公开语义；`vibeflow.io` 是内核节点，不应要求 Python registry 或 JS node descriptor。
- Capability 的声明、Schema 检查和 import 审计不是安全沙箱。重试、回滚、并发安全和真实副作用仍由宿主实现负责。
- TypeScript Compiler API 只提取 VibeFlow ABI、`completion`、Promise 所有权和架构依赖事实；esbuild 负责转译、模块解析和 bundling。完整类型检查、lint、平台 API 兼容性和业务测试属于项目工具。不要把 bundler 专属结构泄漏进 `WorkflowPlan`、descriptor 或公开 Workflow ABI。

配置模型和判定规则位于 `core/config/`，供文件加载使用的 JSON Schema 资源位于 `tooling/project/schema/`；JS 构建脚本与 runtime helper 位于 `targets/javascript/resources/`。wheel 和分发测试直接检查这些正式路径。

当前 JS/TS AOT 支持范围、descriptor 字段、Workflow ABI 和构建 profile 以 `docs/js_aot_build.md` 为准。

## JS/TS AOT 验证

修改 Core、Block Compiler、descriptor loader、JavaScript Target 或 package resources 时，至少运行对应分层测试和独立自检：

```bash
python quality/run.py --profile core
python quality/run.py --profile block-compiler
python quality/run.py --profile javascript-target
PYTHONPATH=src python -m pytest -q tests/core tests/block_compiler tests/targets/javascript
```

最小示例用于快速验证一条真实 descriptor → TypeScript → ESM 链路、三个 profile、Node 执行和确定性构建：

```bash
PYTHONPATH=src python sandbox/javascript/minimal/run_e2e.py --skip-browser
```

JavaScript integration Sandbox 覆盖 node/`base_lib` 数学组合、数据传递、schedule/transfer edge、分支与合流、nodeset、嵌套 override、有界/无界 loop、同步/异步 ABI、Port、Promise node、Capability、取消、trace、detached 清理、completion mismatch、隐藏 Promise、稳定错误码、非法 import、source map、确定性发布和三个 profile：

集成沙箱还覆盖 `vibeflow.plugin.v1` 的 Policy/Compiler/Runtime hook 顺序、依赖闭包、Planned 不绑定实现、同步/异步 completion、构建清单，以及 Host Extension 的真实浏览器 start/stop、Port、取消、双 host 隔离和无 import 副作用。

```bash
npm ci --prefix tools/mermaid-renderer
PYTHONPATH=src python sandbox/javascript/integration/run_all.py \
  --puppeteer-root tools/mermaid-renderer
```

只在没有可用 Chromium/Puppeteer 时使用 `--skip-browser`。发布验收和 CI 不应跳过 browser 测试，因为 `web-app` 的“只注册入口、不自动调用 workflow”契约需要在真实浏览器中验证。

AOT 改动的最低验收还包括：

- Python integration Sandbox 继续通过，证明共享语义与 Python Target 没有回归。
- `esm-module`、`single-esm`、`web-app` 均由项目锁定的 TypeScript/esbuild 构建；VibeFlow 不替项目安装依赖或运行第三方 package scripts。
- 重复调用、并发调用、预取消和执行中取消互不污染；缺失 Capability 在任何 node 执行前失败。
- `single-esm` 没有隐式 companion JavaScript chunk，source map 能定位到原始 node 和 `base_lib`。
- 同一输入、配置和 lockfile 的构建产物保持确定；失败构建不得发布半成品。

## Wheel 与分发包验证

AOT 的 `.mjs` 驱动、runtime helper 和项目 JSON Schema 都是 Python package resources。修改打包配置、资源读取、CLI build 入口或发布模板时，不能只在源码树的 `PYTHONPATH=src` 环境中测试。

先构建 wheel，并在隔离虚拟环境中确认资源和 CLI：

```bash
python -m pip install build
VF_WHEEL_ROOT="$(mktemp -d)"
python -m build --wheel --outdir "$VF_WHEEL_ROOT/dist"
VF_WHEEL="$(find "$VF_WHEEL_ROOT/dist" -maxdepth 1 -name 'vibeflow-*.whl' -print -quit)"
python -m venv "$VF_WHEEL_ROOT/venv"
"$VF_WHEEL_ROOT/venv/bin/python" -m pip install "$VF_WHEEL"
"$VF_WHEEL_ROOT/venv/bin/python" - <<'PY'
from importlib.resources import files

root = files("vibeflow")
resources = (
    "tooling/project/schema/config.schema.json",
    "targets/javascript/resources/toolchain_driver.mjs",
    "targets/javascript/resources/runtime_helpers.mjs",
)
for resource in resources:
    assert root.joinpath(resource).is_file(), resource
PY
"$VF_WHEEL_ROOT/venv/bin/vibeflow" --help
```

再通过根目录构建脚本生成临时分发包，并使用分发包自己的 `run.py` 和压缩内核执行真实 AOT smoke test：

```bash
VF_DIST_ROOT="$(mktemp -d)"
python distribution/build.py \
  --output-dir "$VF_DIST_ROOT/vibeflow-distribution" \
  --archive-dir "$VF_DIST_ROOT/archive"
python "$VF_DIST_ROOT/vibeflow-distribution/run.py" build \
  --config javascript_project/configs/linear.jsonc \
  --target node \
  --profile single-esm \
  --out-dir "$VF_DIST_ROOT/aot"
VF_ENTRY="$VF_DIST_ROOT/aot/index.js" node --input-type=module --eval '
  const {pathToFileURL} = await import("node:url");
  const workflow = await import(pathToFileURL(process.env.VF_ENTRY).href);
  const value = workflow.runWorkflow({x: 10, a: 8, b: 3});
  if (value.result !== 15) {
    throw new Error(JSON.stringify(value));
  }
'
```

临时 smoke test 通过后，运行 `python distribution/build.py` 同时发布 `dist/vibeflow-distribution/` 和版本化 `archive/*.zip`。不要手工编辑生成物：用户文档源位于 `distribution/kernel_development_pack/docs/` 和 `docs/js_aot_build.md`，项目模板源位于 `distribution/kernel_development_pack/project_template/`，内核源位于 `src/vibeflow/`；构建脚本负责双 root 模板、内核归档、manifest、`DISTRIBUTION.json` 和确定性外层 ZIP。

## `review` 编排契约

正式架构审核由统一命令编排，发布包入口和内核入口分别是：

```bash
python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg
PYTHONPATH=src python3 -m vibeflow review \
  --workspace vibeflow_config.jsonc \
  --config project/configs/main.jsonc \
  --output reports/graph.expanded.svg
```

`--config`、`--output` 必填；内核 CLI 的 `--workspace` 必填，发布包 `run.py` 只负责注入自己的 workspace。`--output` 不得与 workspace config、workflow config 或登记的架构文档指向同一路径，否则必须在修改任何源文件前 fail closed。该命令不暴露 collapse、theme、layout、hide-contract、Mermaid limit 等自由参数，始终展开 nodeset、保留完整 contract/semantics，并使用默认主题、透明背景和 canonical `review-columns` composer。

维护实现必须保持以下阶段和失败边界：

1. 加载 workspace，解析 workflow 所属 root，并确认它已在该 root 的 `architecture.documents` 中登记。
2. 在不信任旧架构文档的情况下执行 graph/schema/health preflight；失败时不得更新架构文档或调用 renderer。
3. 重新生成登记的 `ARCHITECTURE.jsonc`，再用 canonical check 做字节级复核。
4. 执行正常 workspace validate，使新架构文档也通过正式门禁。
5. 向临时路径调用 canonical expanded SVG renderer。
6. 解析 SVG XML，确认根元素、`aria-roledescription="flowchart-review-columns"` 和至少一个真实 `review-inline-fragment`。
7. 所有检查通过后才替换目标 SVG；失败时删除临时文件并保留原目标文件。

命令不得调用直接 mmdc fallback，也不得把旧 SVG、expanded MMD 或手写图当作审核成功。renderer 阶段失败后，已经成功更新的架构文档可以保留，但 JSON 结果必须返回 `published: false`。标准输出只写一个 JSON 对象，包含 `status`、`failed_stage`、config、architecture、validation、SVG 路径和 `published`；不写 provenance hash、sidecar 路径或额外人类文本。`PASS` / `CONCERNS` 返回 0，`FAIL` / `ERROR` 返回 1，argparse 参数错误返回 2。

`review` 是正式审核入口；现有 `architecture`、`validate`、`svg` 继续作为单项生成和诊断命令。用户要求“审核后再实现”时，即使 `review` 成功也必须等待后续一条明确的用户批准消息，不能把机器检查成功解释成人类确认。

### `review` 回归测试最低集合

- 已登记的有效 workflow 能更新/生成 canonical 架构文档并发布 expanded SVG。
- 缺失、陈旧或非 canonical 架构文档能被重新生成；未登记 workflow 返回 `REVIEW.ARCHITECTURE.UNREGISTERED` 且不生成 SVG。
- graph/schema/health preflight 失败时，架构文档不变且 renderer 未被调用。
- workspace `CONCERNS` 返回 0 并继续生成审核图。
- renderer 异常或 SVG 为空、不可解析、缺 composer 标记、缺真实 fragment 时不发布，原 SVG 保持不变，并分别报告 `svg` 或 `svg_check` 阶段。
- 发布包入口正确注入 workspace；直接内核入口缺少 `--workspace` 时保持 argparse 错误。
- 普通 SVG 与 `--expand-nodesets` 都经过回归测试，expanded SVG 强制经过 composer。
- 审核产物不生成 `.provenance.json`，也不嵌入 provenance metadata。

## `delegate-cli` 编排契约

CLI 让渡模式 / `delegate-cli` 把一个 workflow 暴露成普通业务 CLI，同时复用 workspace preflight、runtime 和 run artifact 链路。发布包与内核入口分别是：

```bash
python run.py delegate-cli --config project/configs/main.jsonc -- --input data.yaml --verbose
PYTHONPATH=src python3 -m vibeflow delegate-cli \
  --workspace vibeflow_config.jsonc \
  --config project/configs/main.jsonc \
  -- --input data.yaml --verbose
```

`--config` 必填；内核 CLI 的 `--workspace` 必填，发布包 `run.py` 自动注入。首个 `--` 是可选边界：边界前的已知 core 参数由 VibeFlow 消费，未知 token 保持原顺序让渡；边界后所有 token 原样让渡。不得解析、规范化或重排业务 argv。workflow 必须声明 `cli.argv` pipeline input，并声明 `cli.exit_code` 的 `exactly_one` pipeline output requirement；最终唯一 provider 的 key/type 都必须是 `cli.exit_code`。退出值只接受非 bool 的 `int` `0..255`。

业务代码直接使用真实进程 stdin/stdout/stderr。内核不得捕获、重放、重写或添加 JSON/换行，也不得把 VibeFlow banner、warning 或诊断混入业务流。每个新 run 在 `<run-root>/<run-id>/vibeflow.log` 新建日志，记录启动、core 版本提示、失败阶段、artifact 路径和最终退出码；不得记录 argv 原文或业务标准流。显式 `--run-id` 必须是非空的单个路径组件，不能是 `.`、`..`，也不能包含正反斜杠；非法值由 argparse 返回 2 且不创建 run。只有运行目录无法创建时，允许向 stderr 输出最小 VibeFlow 诊断并返回 1。

退出码契约：

- 正常 workflow 的合法 `cli.exit_code`：原样返回 `0..255`。
- `io`、`document`、`data_store` node 或 runtime plugin 抛出的授权 `SystemExit`：`None` 返回 0，合法整数原样返回。
- 缺少 `--config` 或已知 core 参数取值非法：argparse 写 stderr、返回 2，且不得创建 run。
- health、runtime、CLI contract、未授权 `SystemExit`，或 `SystemExit` 值不是合法 `0..255` 整数：返回 1，详细诊断只写 `vibeflow.log`。

`delegate-cli` 不替换 `run` 的机器可读执行/诊断职责，也不改变 `review` 的正式架构审核职责。普通 `run` 仍可输出自己的结构化 CLI 结果；`review` 仍保持单 JSON stdout 与 fail-closed 语义。

`async_flush_timeout` 只限制 runtime 在收尾阶段等待 detached task 的时间，不是命令级强制终止器。Python 已经开始执行的线程不能被安全强杀，解释器退出时仍可能等待它结束；因此 detached 实现必须可协作结束。需要硬性限制整个命令寿命时，应在 VibeFlow 进程外使用进程级隔离和超时，不能把该选项描述成 OS sandbox 或 kill 保证。

### effect scope 维护契约

实现检查使用派生的 `effect_scope`，不能把它做成 workflow config 可任意选择的开关：

| 实现 | effective scope |
| --- | --- |
| 其他普通 implemented node（即非 `io` / `document` / `data_store`，且 `external=False`） | `none` |
| `flow_kind=io` | `terminal` |
| `flow_kind=document` / `data_store` | `python_io` |
| 任意 `external=True` node | `trusted`，优先级最高 |
| plugin | `trusted` |
| planned `python_stub` | `none` |

图形 `flow_kind=terminal` 仍映射到 `none`，不要与 `effect_scope=terminal` 混淆。`terminal` scope 只开放 stdin/stdout/stderr、`print`、`input`、`argparse`；`python_io` 开放文件、环境、网络、数据库、subprocess 和终端；`trusted` 跳过普通实现的副作用限制，但不跳过契约、拓扑、输出和 trace。effectful 或 `external=True` node 的 `CONTRACT.examples` 只能做结构校验，不得在健康检查中执行；planned `python_stub` 继续按 `none` 检查。

### `delegate-cli` 回归测试最低集合

- wrapper 自动注入 workspace，direct kernel 入口要求显式 workspace；首个 `--` 前后 token 的顺序和值保持不变，省略 delimiter 仍可让渡未知 token。
- 业务尾参数即使名为 `--workspace`、`--config` 或其他 core 参数，也不会改变外层解析结果。
- 缺失 `cli.argv` input、缺失/非 `exactly_one` `cli.exit_code` output、provider key/type 不一致、多 provider、bool/非整数/越界退出码全部 fail closed。
- 业务 stdout/stderr 保持逐字节语义；VibeFlow 不增加 JSON、换行或提示，也不捕获 stdin。
- `vibeflow.log` 覆盖启动、版本提示、阶段、artifact 和退出码，不包含 argv 原文与业务流；run 目录创建失败只有最小 stderr。
- 授权和未授权 `SystemExit`、`None`、合法整数、bool、字符串和越界整数分别覆盖；返回码严格符合 0..255、1、2 的契约。
- `none` / `terminal` / `python_io` / `trusted` 的 AST 检查矩阵、`external=True` 最高优先级、plugin trusted、planned `python_stub` none，以及 effectful/external examples 不执行均有回归测试。
- 现有 `run` 的结构化输出、run artifact 和 `review` 的单 JSON stdout/fail-closed 行为保持不变。

## 用户项目质量检查

内置 `quality-check` 按三层工作：

```text
Tooling 读取文件和 workspace
→ Python/JavaScript Target 提取 AST、类型、import 与实现事实
→ Core Quality 统一判定、去重并应用 policy
→ Tooling 输出 text/JSON 和退出码
```

检查用户项目：

```bash
PYTHONPATH=src python -m vibeflow quality-check --path <project>
```

需要检查 Python 隐藏副作用时增加 `--check-side-effects`。文件遍历只在 Tooling；Python AST 和 JavaScript/TypeScript 分析只在对应 Target；Core Quality 只接收普通内存 facts。

## 维护边界

- VibeFlow 仓库自身使用独立 `quality/` profiles，不通过用户项目入口添加仓库特例。
- 修改 Python 审核链路时复用 Core inspection、workspace validation 和 `tooling.application.python.presentation`，不复制解析或渲染链。
- 修改跨语言语义时先更新 Core、Block Compiler 和 conformance fixture，再更新具体 Target。
- 修改用户可见的 JS/TS 配置、ABI、错误码或构建行为时，同步更新 `docs/js_aot_build.md`、JavaScript Sandbox 和分发测试。
- 完成验证后运行 `python tools/clean_workspace.py`。只有预览结果准确时才运行 `--apply`；清理器不处理 `.git/`、`references/` 或 `distribution/` 源模板。
