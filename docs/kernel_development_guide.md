# VibeFlow 开发者工作流

本文档面向维护 VibeFlow（包名 `vibeflow`）自身的开发者，不是面向业务项目编写 node、nodeset 或 plugin 的使用者指南。

VibeFlow 0.12.0 使用分层 API。根包不导出业务对象，维护代码只使用 `vibeflow.core`、`vibeflow.block_compiler`、`vibeflow.targets.*` 和 `vibeflow.tooling.*` 的所属层入口。

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

- `WorkflowPlan` / `BlockPlan` 只保存冻结的 JSON 值、稳定 ID、契约、路由、block 引用和 `SourceRef`，不得保存 Python class、callable、实例或生成后的 Python/JavaScript 源码。当前唯一公共 ABI 是 `vibeflow.workflow.v4`；v3 输入必须显式拒绝，不能靠字段缺省静默升级。
- ABI v4 的 node 计划携带 `effect_scope`、三态 `runtime_dispatch`、`execution_lock`、`contains_global_state`；block/workflow 计划携带适用层级的 `execution_lock` 和 `contains_global_state`。`root_exclusive` 已移除，`contains_global_state` 不隐含锁。`ExecutionLockPlan` 只保存 key 与派生的 `root | block | node` scope，不得保存 Python lock、condition 或 coordinator。
- `PythonBindingPlan` 保存 callable、有效参数和插件引用；`JavascriptBindingPlan` 保存 JS/TS 源码、Schema、base_lib、Plugin、Capability、Host Extension 和 import policy。两者都不能进入公共 IR。
- Python Runtime 支持 `ExecutionPlan` 与 plan/block/compiled 三种模式；这些对象属于 Python Target，不进入公共 IR。
- JavaScript emitter 以 `WorkflowPlan + JavascriptBindingPlan` 为语义来源。
- Core 和 Block Compiler 不得做文件、环境、动态 import、subprocess 或语言实现操作；两个 Target 不得互相 import。
- Core 的 `TargetFeatureSet` 以 `global_state`、`execution_locks` 标记 Target 能力。implemented 语义需要而 Target 未声明时必须以 `TARGET.FEATURE.UNSUPPORTED` fail closed；不能由 Tooling 猜测或降级改写。
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

### `global_state` 与 execution lease 维护契约

`flow_kind=global_state` 是 Core 拥有的语言无关语义，不是 Python Target 私有 config，也不是 `vibeflow.global_state` 系统 node。Core 负责合法 flow kind、派生 `effect_scope=global_state`、feature gating、`runtime_dispatch` 实现事实和 `contains_global_state` 事实；Block Compiler 负责把事实递归传播到 nodeset/loop、生成 ABI v4 字段并验证显式锁的异步与嵌套顺序；Target 决定自己的 ambient state 与 runtime-dispatch 检测方式并实现审计、锁与 trace。当前只有 Python Target 声明 `global_state` 和 `execution_locks`，JavaScript Target v1 两项都不声明。

Python 的 global-state scope 容纳当前进程内 Python/module/native-library 的易失 ambient state，以及从 envelope、registry、cache 或运行时对象取得的 callback/方法分派。该边界不能扩张为直接文件、环境变量、网络、数据库、终端、subprocess、线程/进程创建、`eval` / `exec` / `compile`、动态 import、`ctypes` / `cffi` 或任意 FFI；可识别的系统级 callback 逃逸同样拒绝。项目源码、本地 helper 和静态 import chain 均须完整分析；静态第三方计算库 import 本身不等于 external。只有 wrapper 实现源码不可取得、不可解析或不可审查时才进入 `external=True` / `trusted`。examples 只做结构检查。model、optimizer、scheduler、DataLoader 等普通对象继续沿现有 envelope / contract 以引用流转；不得为 global-state 另建 Provider、隐式数据通道或另一套对象协议。

维护者不得把这套 AST 规则描述成安全沙箱：它是合作式架构与质量审计，只拒绝可识别的直接越权操作，不承诺证明任意第三方或 native 函数内部没有隐藏 IO。静态 API 内部不可见的行为不强行推断，也不因此自动要求 `external=True`。

runtime-dispatch analyzer 必须独立于 effect-name gate 和 import metadata preflight。它只报告源码可见、高置信度的运行时 callable/receiver 分派，跟踪 envelope/registry/cache 来源、赋值、属性、下标、分支、闭包和可解析本地 helper；不得执行 example/callback，也不得维护 Torch/NumPy 等工具白名单。固定 builtin、Python 隐式协议、只读 Mapping 的 `get/keys/values/items`、静态 import/构造调用、只传递未调用的 callable，以及静态第三方/native API 内部不可见行为均不报告。`print`/`input`/`argparse` 与文件、Path、网络、数据库、subprocess 仍交给原有 effect analyzer。普通 `none` scope 只得到 warning；`global_state` 和既有 IO effect scope 抑制这条 warning，但 `runtime_dispatch` 事实仍进入计划和 Architecture。

Python import preflight 必须先读取完整本地 source graph，再以固定点方式证明导入期声明 helper 和本地基类。允许与否只能由已解析源码、有限控制结构、闭合调用链以及 effect 检查决定，不得维护 `REQ`、`PROV` 或项目模块名白名单。跨模块 helper 内的任一未解析调用、循环/递归、动态代码、IO、线程/进程、FFI 或 ambient-state 修改都必须让调用者保持未证明状态；本地基类存在 metaclass、`__init_subclass__` 或未解析父类时同样拒绝。静态预检通过后，加载出的每个 node 仍按其真实 `effect_scope` 执行现有完整 class/module quality 检查。

语义默认持久且非事务：runtime 不 snapshot、rollback 或自动恢复 ambient state，成功、异常和取消都一样。若一个操作只需临时改变状态并要求可靠恢复，业务实现必须在同一个 global-state node 内用 `try/finally` 恢复；锁本身不提供事务或恢复。维护代码和错误文本都不能暗示失败后已恢复。

公开配置只接受 `pipeline.execution_lock: {"key": "..."}` 与 `pipeline.nodes[].execution_lock: {"key": "..."}`。`ExecutionLockSpec` 只含规范化的非空 key；`vibeflow.` 前缀保留。scope 由编译位置派生，显式锁不提供任何副作用权限。外层已经持有用户 key 时，嵌套 block/node 只能复用同一 key；不同 key 必须在 Block Compiler 和 runtime planning 双重拒绝。planned global-state 只用于 Architecture/review，不加入 `contains_global_state`、不触发 feature/独占锁，也不可执行。

Python root 不再为 global-state 自动获取 shared/exclusive ambient-state lease。只有非空显式 `execution_lock` 才进入协调器：同 key 互斥，不同 key 并行，无 key 的 global-state 正常执行并产生建议性 warning。pipeline 命名锁以 exclusive root/block scope 获取，调用点锁以 exclusive node scope 获取。嵌套 runtime 和受管理线程继承同一 lease，重入按 lease id 而不是线程 id；release 必须晚于 success/failure hooks、受保护 future drain 和 executor shutdown。异常路径也必须成对释放，且不得让 future 逃出显式锁 scope。

任一显式锁保护作用域都禁止 detached。`result_key` 只有静态存在无条件 scheduled consumer path、能够保证 join 时才合法；Core、Block Compiler 与 Python runtime planning 必须一致校验，runtime 收尾再作 fail-safe drain。无锁 global-state 使用普通异步规则。Architecture JSON、Mermaid 与 SVG 应显示 `effect_scope`、`runtime_dispatch`、有效 execution lock（无锁时为 `none`）和 `contains_global_state`；global-state 使用 cloud 图例，不展示 Provider 权限。boundary/full trace 始终保留 `global_state_enter`、`global_state_exit`，只为显式锁记录 wait/acquire/release，失败且 global-state 已开始时追加 `global_state_may_have_changed`。

该语义的最低回归覆盖应跨 Core、Block Compiler、Python Target 和 JS Target：递归传播与 planned 排除、ABI v3 拒绝/v4 round-trip、feature gating、三态 runtime-dispatch、同 key 可重入与异 key 嵌套拒绝、无锁 global-state 并行与 warning、同 key 串行/异 key 并行、hooks/异步收尾之后才释放、异常释放和 may-have-changed trace、仅显式锁 scope 的 detached/result join 门禁，以及 JS 统一的 `TARGET.FEATURE.UNSUPPORTED`。检测回归必须覆盖普通 callback warning、global-state/IO scope 抑制、builtin/协议/静态调用不误报。图形回归还要覆盖 shared cloud shape helper、Architecture 字段和 Python/JS review SVG。

修改上述语义后必须运行完整 Python integration Sandbox，而不能只依赖单元测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python sandbox/python/integration/run_all.py
```

其中专门案例会验证 global-state examples 不执行、禁止副作用矩阵、WorkflowPlan v4 与 Architecture 传播、runtime-dispatch 检测及 IO/builtin 误报回归、无锁 warning、同 key 重入/串行和异 key 并行、失败释放、仅显式锁 scope 的 detached/unjoined result 拒绝，以及 mmdc 生成 SVG 中的 cloud path。trace 案例必须确认无锁 cloud 不产生锁事件，显式锁仍严格保持 wait/acquire/release 的数量、顺序、reentrant、wait time 和 run ID。

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
6. 解析 SVG XML，确认根元素、`aria-roledescription="flowchart-review-columns"` 和非空 `review-inline-fragment`，并用 `data-review-kind`、`data-review-owner`、`data-review-target` 对照审核快照的预期覆盖集合；缺失、重复或意外 fragment 都以 `REVIEW.SVG.COVERAGE` 失败。
7. 所有检查通过后才替换目标 SVG；失败时删除临时文件并保留原目标文件。

命令不得调用直接 mmdc fallback，也不得把旧 SVG、expanded MMD 或手写图当作审核成功。Python 与 JavaScript 都从各自 adapter 构造同一语言无关审核快照，再进入同一个 canonical composer；JavaScript Application 不得导入 Python Target/Application。renderer 阶段失败后，已经成功更新的架构文档可以保留，但 JSON 结果必须返回 `published: false`。标准输出只写一个 JSON 对象，包含 `status`、`failed_stage`、config、architecture、validation、SVG 路径和 `published`；0.12.0 的 JavaScript 输出暂时保留 `project_target` 与旧 `output` 别名。不写 provenance hash、sidecar 路径或额外人类文本。`PASS` / `CONCERNS` 返回 0，`FAIL` / `ERROR` 返回 1，argparse 参数错误返回 2。

`review` 是正式审核入口；现有 `architecture`、`validate`、`svg` 继续作为单项生成和诊断命令。用户要求“审核后再实现”时，即使 `review` 成功也必须等待后续一条明确的用户批准消息，不能把机器检查成功解释成人类确认。

### `review` 回归测试最低集合

- 已登记的有效 workflow 能更新/生成 canonical 架构文档并发布 expanded SVG。
- 缺失、陈旧或非 canonical 架构文档能被重新生成；未登记 workflow 返回 `REVIEW.ARCHITECTURE.UNREGISTERED` 且不生成 SVG。
- graph/schema/health preflight 失败时，架构文档不变且 renderer 未被调用。
- workspace `CONCERNS` 返回 0 并继续生成审核图。
- renderer 异常或 SVG 为空、不可解析、缺 composer 标记、缺真实 fragment、覆盖集合缺失/重复/意外时不发布，原 SVG 保持不变，并分别报告 `REVIEW.SVG.RENDER`、结构错误或 `REVIEW.SVG.COVERAGE`。
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
| 其他普通 implemented node（即非 `io` / `document` / `data_store` / `global_state`，且 `external=False`） | `none` |
| `flow_kind=io` | `terminal` |
| `flow_kind=document` / `data_store` | `python_io` |
| `flow_kind=global_state` 且 `external=False` | `global_state` |
| 任意 `external=True` node | `trusted`，优先级最高 |
| plugin | `trusted` |
| planned `python_stub` | `none` |

图形 `flow_kind=terminal` 仍映射到 `none`，不要与 `effect_scope=terminal` 混淆。`terminal` scope 只开放 stdin/stdout/stderr、`print`、`input`、`argparse`；`python_io` 开放文件、环境、网络、数据库、subprocess 和终端；`global_state` 容纳当前进程易失 ambient state 与 runtime dispatch，明确不继承 `terminal` 或 `python_io`；`trusted` 跳过普通实现的副作用限制，但不跳过契约、拓扑、输出和 trace。effectful 或 `external=True` node 的 `CONTRACT.examples` 只能做结构校验，不得在健康检查中执行；planned `python_stub` 继续按 `none` 检查。

### `delegate-cli` 回归测试最低集合

- wrapper 自动注入 workspace，direct kernel 入口要求显式 workspace；首个 `--` 前后 token 的顺序和值保持不变，省略 delimiter 仍可让渡未知 token。
- 业务尾参数即使名为 `--workspace`、`--config` 或其他 core 参数，也不会改变外层解析结果。
- 缺失 `cli.argv` input、缺失/非 `exactly_one` `cli.exit_code` output、provider key/type 不一致、多 provider、bool/非整数/越界退出码全部 fail closed。
- 业务 stdout/stderr 保持逐字节语义；VibeFlow 不增加 JSON、换行或提示，也不捕获 stdin。
- `vibeflow.log` 覆盖启动、版本提示、阶段、artifact 和退出码，不包含 argv 原文与业务流；run 目录创建失败只有最小 stderr。
- 授权和未授权 `SystemExit`、`None`、合法整数、bool、字符串和越界整数分别覆盖；返回码严格符合 0..255、1、2 的契约。
- `none` / `terminal` / `python_io` / `global_state` / `trusted` 的 AST 检查矩阵、global-state 明确 deny 边界、`external=True` 最高优先级、plugin trusted、planned `python_stub` none，以及 effectful/external examples 不执行均有回归测试。
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
- 修改 `global_state` 或 `execution_lock` 时同时维护语言无关 ABI/feature 判定、Python ambient-state 审计与 lease 生命周期、JS unsupported 门禁、Architecture/trace/cloud 图例；不得只在 Python AST 规则中增加特例。
- 修改用户可见的 JS/TS 配置、ABI、错误码或构建行为时，同步更新 `docs/js_aot_build.md`、JavaScript Sandbox 和分发测试。
- 完成验证后运行 `python tools/clean_workspace.py`。只有预览结果准确时才运行 `--apply`；清理器不处理 `.git/`、`references/` 或 `distribution/` 源模板。
