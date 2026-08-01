# VibeFlow 开发者工作流

本文档面向维护 VibeFlow（包名 `vibeflow`）自身的开发者，不是面向业务项目编写 node、nodeset 或 plugin 的使用者指南。

## 基本验证流程

修改 VibeFlow 代码后，默认运行以下命令：

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
python3 -m compileall -q src tests examples
PYTHONPATH=src python3 examples/integration_sandbox/run_all.py
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

其中最后一条是通用代码质量自检。它不再有仓库专属的 `--self` 模式；检查 VibeFlow 仓库自身时统一传入当前仓库路径 `.`。

验收标准：

- `quality-check` 必须输出 `PASS`。
- `errors` 必须为 `0`。
- `warnings` 必须为 `0`。
- 若新增代码触发 warning，优先重构新增代码；不要为了通过检查而随意放宽通用质量规则。

阅读 `quality-check` 结果时，先看每条 finding 的 `object_type:object_id` 和 source location，再看 `details`。文本输出会打印紧凑 `details:` 行；JSON 输出保留完整结构。重复函数、依赖环、双向依赖、跨目录/内部模块 import 等 warning 会在 details 中列出具体函数、import site、source/target module 和建议 public entry，优先改这些位置。

## 可移植计划与 JS/TS AOT 维护边界

跨语言链路以 `vibeflow.portable` 中的不可变、语言无关计划为边界：

```text
GraphConfig + CompiledGraph / ExecutionPlan
  -> WorkflowPlan
     -> BlockPlan
        -> NodeCallPlan + RoutePlan + ConditionPlan + TaskPlan
  -> JS/TS AOT 规范化与静态 JavaScript emitter
  -> 普通 ESM / Web 构建产物
```

维护这条链路时必须保持：

- `WorkflowPlan` / `BlockPlan` 只保存冻结的 JSON 值、稳定 ID、契约、路由、block 引用和 `SourceRef`，不得保存 Python class、callable、实例或生成后的 Python/JavaScript 源码。
- 现有 Python runtime 仍使用 `ExecutionPlan`；其 `to_workflow_plan()` 是兼容投影。不要把“已经有可移植计划”描述成“Python runtime 已经改由 emitter 执行”，也不要复制一套与 Python 调度语义分叉的 AOT 图解释器。
- node、`base_lib`、data schema、Capability 和 Host Extension 使用静态 JSONC descriptor 建模。已有 Python registry 通过兼容层转成 descriptor；静态 descriptor 与 Python 注册同时存在时必须做一致性检查。
- JavaScript emitter 根据 `entry_mode` 输出同步 `runWorkflow()` 或异步 `runWorkflowAsync()`，不是把原始流程图或通用 graph walker 搬进目标环境。生成模块被 import 时不得执行业务 workflow 或启动扩展。
- Capability descriptor 只定义依赖契约。实现由宿主在每次调用时注入或由 Host Extension 提供；调用状态、trace、任务和 Capability wrapper 不得保存在可变模块级业务状态中。
- `descriptors.host_extensions` 登记 project 可用扩展，workflow 顶层
  `host_extensions` 选择本流程实际使用的资源。implemented 扩展解析、检查并
  打包；planned 扩展只进入 Architecture JSON 和图形审查，不参与生命周期或
  Capability 提供。旧 `javascript.host_extensions` 仅作为没有 workflow 字段时
  的兼容默认值。
- `completion`、`schedule`、`executor` 必须分开建模；同步 JS 计划不得包含 suspend/deferred/detached。TypeScript 源码审计负责拒绝声明不实和未归属 Promise，不增加运行时 thenable 兜底。
- `max_iterations: null`、组合 stop 和无 stop 永久 loop 是公开语义；`vibeflow.io` 是内核节点，不应要求 Python registry 或 JS node descriptor。
- Capability 的声明、Schema 检查和 import 审计不是安全沙箱。重试、回滚、并发安全和真实副作用仍由宿主实现负责。
- TypeScript Compiler API 负责类型与源码依赖检查，esbuild 负责 bundling。不要把 bundler 专属结构泄漏进 `WorkflowPlan`、descriptor 或公开 Workflow ABI。

当前 JS/TS AOT 支持范围、descriptor 字段、Workflow ABI 和构建 profile 以 `docs/js_aot_build.md` 为准；`docs/14_JS_TS节点与Web_AOT构建计划.md` 是设计记录，不能作为当前 API 的事实来源。

## JS/TS AOT 验证

修改 portable plan、descriptor loader/catalog、AOT Schema、emitter、构建器、Node 工具链驱动或其 package resources 时，至少运行相关单元测试：

```bash
PYTHONPATH=src python -m pytest -q \
  tests/unit/test_aot_core.py \
  tests/unit/test_strict_typescript_sandbox.py \
  tests/unit/test/strict_aot_*.py
```

最小示例用于快速验证一条真实 descriptor → TypeScript → ESM 链路、三个 profile、Node 执行和确定性构建：

```bash
npm ci --prefix examples/js_aot_minimal/project
PYTHONPATH=src python examples/js_aot_minimal/run_e2e.py --skip-browser
```

完整 TypeScript 沙箱覆盖 node/`base_lib` 数学组合、数据传递、schedule/transfer edge、分支与合流、nodeset、嵌套 override、有界/无界 loop、同步/异步 ABI、Port、Promise node、Capability、取消、trace、detached 清理、completion mismatch、隐藏 Promise、稳定错误码、非法 import、source map、确定性发布和三个 profile：

```bash
npm ci --prefix examples/typescript_sandbox/project
npm ci --prefix tools/mermaid-renderer
PYTHONPATH=src python examples/typescript_sandbox/run_all.py \
  --puppeteer-root tools/mermaid-renderer
```

只在没有可用 Chromium/Puppeteer 时使用 `--skip-browser`。发布验收和 CI 不应跳过 browser 测试，因为 `web-app` 的“只注册入口、不自动调用 workflow”契约需要在真实浏览器中验证。

AOT 改动的最低验收还包括：

- Python integration sandbox 继续通过，证明原有 Python 项目和 `ExecutionPlan` 兼容链没有回归。
- `esm-module`、`single-esm`、`web-app` 均由项目锁定的 TypeScript/esbuild 构建；VibeFlow 不替项目安装依赖或运行第三方 package scripts。
- 重复调用、并发调用、预取消和执行中取消互不污染；缺失 Capability 在任何 node 执行前失败。
- `single-esm` 没有隐式 companion JavaScript chunk，source map 能定位到原始 node 和 `base_lib`。
- 同一输入、配置和 lockfile 的构建产物保持确定；失败构建不得发布半成品。

## Wheel 与分发包验证

AOT 的 `.mjs` 驱动和 runtime helper 是 Python package resources。修改打包配置、资源读取、CLI build 入口或发布模板时，不能只在源码树的 `PYTHONPATH=src` 环境中测试。

先构建 wheel，并在隔离虚拟环境中确认资源和 CLI：

```bash
python -m pip install build
VF_WHEEL_ROOT="$(mktemp -d)"
python -m build --wheel --outdir "$VF_WHEEL_ROOT/dist"
VF_WHEEL="$(find "$VF_WHEEL_ROOT/dist" -maxdepth 1 -name 'vibeflow-*.whl' -print -quit)"
python -m venv "$VF_WHEEL_ROOT/venv"
"$VF_WHEEL_ROOT/venv/bin/python" -m pip install "$VF_WHEEL"
"$VF_WHEEL_ROOT/venv/bin/python" -c \
  'from importlib.resources import files; root = files("vibeflow").joinpath("aot/resources"); assert root.joinpath("toolchain_driver.mjs").is_file(); assert root.joinpath("runtime_helpers.mjs").is_file()'
"$VF_WHEEL_ROOT/venv/bin/vibeflow" --help
```

再通过根目录构建脚本生成临时分发包，并使用分发包自己的 `run.py` 和压缩内核执行真实 AOT smoke test：

```bash
VF_DIST_ROOT="$(mktemp -d)"
python build_distribution.py --output "$VF_DIST_ROOT/distribution"
python "$VF_DIST_ROOT/distribution/run.py" build \
  --workspace examples/js_aot_minimal/vibeflow_config.jsonc \
  --config examples/js_aot_minimal/project/configs/greeting.jsonc \
  --target node \
  --profile single-esm \
  --out-dir "$VF_DIST_ROOT/aot"
VF_ENTRY="$VF_DIST_ROOT/aot/index.js" node --input-type=module --eval '
  const {pathToFileURL} = await import("node:url");
  const workflow = await import(pathToFileURL(process.env.VF_ENTRY).href);
  const value = await workflow.runWorkflowAsync(
    {name: "  Release Smoke "},
    {capabilities: {"example.clock": {now: async () => 123}}},
  );
  if (value.greeting !== "Hello, Release Smoke! (123)") {
    throw new Error(JSON.stringify(value));
  }
'
```

临时 smoke test 通过后，正式更新仓库根目录的分发产物时运行 `python build_distribution.py`。不要手工编辑生成的 `vibeflow_distribution/`：用户文档源位于 `distribution/kernel_development_pack/docs/` 和 `docs/js_aot_build.md`，项目模板源位于 `distribution/kernel_development_pack/project_template/`，内核源位于 `src/vibeflow/`；构建脚本负责复制、封装并重写 `kernel/MANIFEST.sha256`。

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
- 现有普通 SVG 与 `--expand-nodesets` 行为保持兼容，expanded SVG 仍强制经过 composer。
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

业务代码直接使用真实进程 stdin/stdout/stderr。内核不得捕获、重放、重写或添加 JSON/换行，也不得把 VibeFlow banner、warning 或诊断混入业务流。每个新 run 在 `<run-root>/<run-id>/vibeflow.log` 新建日志，记录启动、core 兼容提示、失败阶段、artifact 路径和最终退出码；不得记录 argv 原文或业务标准流。显式 `--run-id` 必须是非空的单个路径组件，不能是 `.`、`..`，也不能包含正反斜杠；非法值由 argparse 返回 2 且不创建 run。只有运行目录无法创建时，允许向 stderr 输出最小 VibeFlow 诊断并返回 1。

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
- `vibeflow.log` 覆盖启动、兼容提示、阶段、artifact 和退出码，不包含 argv 原文与业务流；run 目录创建失败只有最小 stderr。
- 授权和未授权 `SystemExit`、`None`、合法整数、bool、字符串和越界整数分别覆盖；返回码严格符合 0..255、1、2 的契约。
- `none` / `terminal` / `python_io` / `trusted` 的 AST 检查矩阵、`external=True` 最高优先级、plugin trusted、planned `python_stub` none，以及 effectful/external examples 不执行均有回归测试。
- 现有 `run` 的结构化输出、run artifact 和 `review` 的单 JSON stdout/fail-closed 行为保持不变。

## 副作用扫描

通用质量工具默认做结构、依赖图和重复逻辑检查。维护质量工具本身、运行时入口、边界层或其他可能引入 IO 的代码时，可以额外运行：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path . --check-side-effects
```

这个选项用于发现文件、网络、数据库、外部进程、环境变量和动态执行等隐藏副作用风险。node/base_lib 的强纯度检查仍由 VibeFlow 自己的 node 健康检查负责，不依赖这个通用选项。

## 维护边界

- `quality-check` 是通用 Python 代码质量工具，不要求目标项目使用 `vibeflow` 架构。
- VibeFlow 仓库自身也通过 `--path .` 使用同一套通用规则自检。
- 不应重新添加只服务本仓库的 `quality-check --self` 分支；仓库专用排除项应通过通用路径扫描规则表达。
- 示例、文档和测试变更也需要经过最终自检，避免维护性 warning 被带入主线。
- 修改审核链路时应优先复用 architecture、workspace validate 和 canonical renderer 的公开内部能力；不要复制一套平行解析、验证或 Mermaid 渲染实现。
- 修改跨语言语义时应先更新 portable plan 和共同 conformance fixture，再更新具体 emitter；不要只在 JavaScript 模板里修补语义。
- 修改用户可见的 JS/TS 配置、ABI、错误码或构建行为时，应同步更新 `docs/js_aot_build.md`、相关示例和分发包测试；修改维护流程或长期边界时，再分别更新本文和 `docs/kernel_target_vision.md`。
