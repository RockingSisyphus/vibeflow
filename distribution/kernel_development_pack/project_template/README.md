# VibeFlow 可复制开发包

版本：0.10.0

这个目录可以整体复制到其他位置作为新项目起点。它包含一个通用 kernel、内核文档、AI 开发提示词，以及相互隔离的 Python 和 JavaScript 示例 root。`DISTRIBUTION.json` 记录版本、root 和内核 hash。

开始开发前，AI 和开发者都应先阅读 `AGENTS.md`，并按任务类型工作：

- 新建项目（greenfield）可以从粗粒度 planned 流程开始。
- 修改已有项目（existing）先读 `python_project/ARCHITECTURE.jsonc`，沿 source 定位真实 workflow config 及其导入 nodeset，然后原位修改。不为审核新建平行 config，不用概念图替代真实 config。

修改后用 `python run.py review` 完成正式架构审核。任务判定、`复用 / 修改 / 删除 / 新增`清单和人类批准门见 `AGENTS.md`。

VibeFlow 提供两条开发路径：

- **Python Runtime**：Python node、base_lib 和 plugin 分别放在
  `python_project/nodes/`、`python_project/base_lib/` 和 `python_project/plugins/`，并在
  `python_project/registry.py` 注册；使用 `run`、`review` 和 `delegate-cli`。
- **JavaScript/TypeScript AOT**：JS/TS node 与 base_lib 放在
  `javascript_project/nodes/`、`javascript_project/base_lib/`，Plugin 与 Host Extension 放在
  `javascript_project/plugins/`、`javascript_project/host_extensions/`，六类 JSONC descriptor 放在
  `javascript_project/manifests/{nodes,base_lib,data,capabilities,plugins,host_extensions}/`，可选 Web 模板和应用
  入口放在 `javascript_project/web/`；使用 `build` 生成普通 ESM 或网页。构建产物运行时
  不需要 Python，也不需要 VibeFlow Runtime。

正式 Target 名是 `javascript`；TypeScript 是该 Target 支持的实现语言。

根目录 `vibeflow_config.jsonc` 声明两个 workspace roots。每个 root 的
`vibeflow_project.jsonc` 用必填 `project_target` 选择 `python` 或 `javascript`；
Python root 声明 Registry/Runtime，JavaScript root 声明 descriptor/工具链。单次
workflow 和 nodeset import 不跨 Target。

常用命令：

```powershell
python run.py architecture --config python_project/configs/main.jsonc --output python_project/ARCHITECTURE.jsonc
python run.py architecture --config python_project/configs/main.jsonc --output python_project/ARCHITECTURE.jsonc --check
python run.py review --config python_project/configs/main.jsonc --output reports/graph.expanded.svg
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --run-root runs
python run.py review --config javascript_project/configs/linear.jsonc --output reports/javascript.svg
python run.py build --config javascript_project/configs/linear.jsonc --target node --profile single-esm --out-dir output/node
python run.py build --config javascript_project/configs/linear.jsonc --target browser --profile web-app --html javascript_project/web/index.template.html --app-entry javascript_project/web/app.ts --out-dir output/web
python run.py delegate-cli --config python_project/configs/main.jsonc -- --input data.yaml --verbose
python run.py mermaid --config python_project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config python_project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config python_project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config python_project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
python run.py quality --path python_project
python run.py verify-kernel
```

JS/TS AOT 项目需要在 `javascript_project/vibeflow_project.jsonc` 的 `descriptors`
字段登记 node、base_lib、Data Schema、Capability、Plugin 和 Host Extension descriptor，并用
`javascript.package_root` 指向本地 `package.json`、lockfile 和
`node_modules`。项目自行安装并锁定 Node.js、TypeScript 与 esbuild；
VibeFlow 不会执行 `npm install` 或第三方 package scripts。完整 descriptor、
Node/Workflow ABI、`vibeflow.plugin.v1`、同步/异步入口、Port、Capability、Host Extension、三种 profile 与 `web-app` 入口规则见
`kernel/docs/11_JS_TS与Web_AOT构建指南.md`。`javascript_project/` 本身是可直接
validate、review 和 build 的数学示例，包含登记的 `ARCHITECTURE.jsonc`、TS Node、
base_lib、Plugin、Capability 和 Host Extension。包内另有
`configs/browser_permanent_port_host.jsonc`，用于验证真实浏览器中的无界 loop、
Port、Host 实例隔离和取消。完整的语义与反例 Sandbox 只保留在 VibeFlow 源码仓库，
不复制进正式分发包。

workflow 不声明 Browser/Node 平台。`validate`、`review` 和 `quality` 关注
VibeFlow 图与架构契约；每次 `build --target` 选择本次构建的实现并调用
esbuild。完整 TypeScript 类型、lint、平台 API 兼容性和业务结果由项目自己的
工具与真实宿主测试负责。

`descriptors.plugins` 与 `descriptors.host_extensions` 只登记 project 可用资源；
每个 workflow 在顶层 `plugins` / `host_extensions` 中选择实际使用项。Planned
资源进入 Architecture JSON 与 Mermaid/SVG，但不解析源码、不执行、不打包，也
不提供 Capability；implemented 资源不能依赖 planned 资源。

默认项目把 `python_project/configs/main.jsonc` 登记到 `python_project/ARCHITECTURE.jsonc`。这是带固定“生成且不可执行”头注释的单文件架构审查文档，不是 workflow config；AI 和开发者应先用它理解入口流程、nodeset 调用、节点职责、数据契约、资源和配置来源。架构变更必须落到真实 workflow config、相关 nodeset、registry metadata/config schema 或资源声明中。正式 `review` 会自动重新生成登记文档、执行正式 validate，并且只在 canonical expanded SVG 结构检查通过后发布 SVG；失败时不得用 mmdc、手写 SVG 或旧产物补位。

CLI 让渡模式 / `delegate-cli` 用于把 workflow 当成普通业务 CLI。首个 `--` 可选地分隔 core 与业务参数；让渡 token 以 `cli.argv` 进入图，图以唯一 `cli.exit_code` 返回非 bool 整数 `0..255`。业务使用真实 stdin/stdout/stderr，VibeFlow 诊断只写当次 run 的 `vibeflow.log`。授权 `SystemExit(None)` 返回 0，合法整数原样返回；框架/未授权退出错误返回 1，已知 core 参数的 argparse 错误返回 2。详细终端/IO/授权规则见 `kernel/docs/07_启动命令与报告.md`。`run` 与 `review` 的原职责不变。

副作用权限由内核派生：普通 implemented node 和 planned `python_stub` 是 `none`；`flow_kind=io` 是 `terminal`；`document` / `data_store` 是 `python_io`；任意 `external=True` node 和 plugin 是最高优先级 `trusted`。图形 `flow_kind=terminal` 仍是 `none`。effectful / external node 的 examples 只检查结构，不执行。

## 读取 Python Runtime 真实运行结果

自定义 adapter 或启动器调用 `run_workspace_checked(...)` / `run_checked(...)` 后，应从返回的 `CheckedRunResult.context` 读取真实 envelope：

```python
value = result.context.get("response.value")["value"]
```

`input_summary.json`、`output_summary.json` 和 trace 只保存脱敏摘要。其中的 `"scalar": true` 只表示原值是标量，不是业务布尔值 `True`，也无法区分 `True` 和 `False`。不要解析 `output_summary.json` 作为业务输出，也不要对摘要字典做 `bool(...)`。

JS/TS AOT 不使用 `CheckedRunResult`：`entry_mode` 缺省 `sync`，宿主调用
直接返回值的 `runWorkflow(inputs, options)`；显式异步 workflow 调用
`await runWorkflowAsync(inputs, options)`。成功结果都是生成类型声明中定义的
普通业务对象，同步失败直接抛错，异步失败 reject。单纯 import 不会自动执行
workflow 或 Host Extension；Capability、trace 和 `AbortSignal` 通过每次调用
的 `options` 注入，或由显式 `createWorkflowHost()` 管理。

配置文件分两层：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局
policy。Python Runtime root 的 `vibeflow_project.jsonc` 声明 registry、quality、
可选 runtime 参数和 `architecture.documents`；可用的 Python
node/base_lib/plugin 在 `python_project/registry.py` 注册，每个 workflow config 用
id 声明本流程实际使用哪些 base_lib/plugin。JS/TS AOT root 改用
`descriptors` 声明静态资源目录、用 `javascript` 声明工具链根和 external
packages；JavaScript Target 直接使用 descriptor，无需 Python registry。分发包默认是：

```jsonc
{
  "policy": {},
  "roots": [
    {"id": "python-project", "path": "python_project"},
    {"id": "javascript-project", "path": "javascript_project"}
  ]
}
```

每个 root 下都需要自己的 `vibeflow_project.jsonc`。Python `registry` 和 AOT
descriptor/source 路径都相对所属 root 解析。`runtime.async_max_workers` 控制
该 root 内每个 Python Runtime 自有线程池的并发数（默认 4），
`runtime.async_flush_timeout` 控制 detached task 的收尾等待时间，
`runtime.nodeset_max_depth` 控制普通 nodeset 与 loop body 的最大静态嵌套深度
（默认 4）。`architecture.documents` 用 root-relative `workflow` /
`document` 登记需要强制保持新鲜的架构文档。Python
`build_base_lib_registry()` / `build_plugin_registry()` 中的 module 或文件路径
也按该 root 解析。`quality.structure` 使用 warning/error 双阈值治理 Python
root 代码布局，默认允许最多 120 个 `.py`，但单个代码目录超过 16 个 `.py`
会失败，用来推动 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。Python
pipeline config 不再声明 `policy`，但必须声明本 workflow 实际使用的资源：

```jsonc
{
  "base_lib": {"modules": [{"id": "math_tools"}]},
  "plugins": [{"id": "project_policy", "config": {"level": "strict"}}],
  "pipeline": {"nodes": [], "edges": []}
}
```

审查图和 `health_report.json.info.resources` 只展示当前 workflow 实际引用的资源；`available_resources` 才展示 root registry 中可用但未必使用的资源。跨 root nodeset import 使用：

```jsonc
{
  "nodeset_imports": [
    {"root": "training_project", "path": "configs/nodesets/train_step.jsonc"}
  ]
}
```

`run` 会在 `runs/<run_id>/` 自动写出快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。external implemented node 在原有形状上使用 `[EXTERNAL]` 标题和 `7px` non-scaling 粗边框。expanded SVG 只在同一父图内合并调用种类和 `type_key` 都相同的直接 nodeset 详情，父图调用点和连边不删除，不同父图分别展开。VibeFlow 命令内部使用 bundled Mermaid CLI 渲染 SVG；Mermaid CLI/mmdc 是实现细节，不是公开审核入口。普通单项 `svg` 命令保留图形导出/诊断参数，正式架构审核则使用参数固定的 `review`。

`run` 还会在当次运行目录写出预期的 `architecture.jsonc` 供审计，但不会替你覆盖 root 中登记的 `python_project/ARCHITECTURE.jsonc`。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用，仍按调用点展开且不做局部详情去重。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG；正式审核使用 `python run.py review --config ... --output ...`。

如果要使用 `svg`，确保项目根目录存在 `kernel/tools/mermaid-renderer/`，并先执行：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

`kernel/docs/`、`kernel/tools/`、`kernel/LICENSE` 和
`kernel/THIRD_PARTY_NOTICES.md` 是随内核分发的只读参考材料；根目录
`README.md`、`AGENTS.md` 和项目自己的说明可以按项目定制。分发包不内置
`.gitignore`，建议项目自行忽略
`kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、
`__pycache__/` 和 `*.pyc`。

模板中的最小 flow 是：

```text
terminal start -> process seed -> process add -> io output -> terminal end
```

可复用 nodeset 放在 `python_project/configs/nodesets/` 的独立 JSONC 文件中，根对象声明 `type_key`；主 config 通过 `nodeset_imports` 导入，并在调用点把该 `type_key` 写进 `type_used`。

implemented nodeset 必须包含完整 pipeline。planned nodeset 可以只保留契约占位，也可以带 planned body 逐步细化；body 会出现在 `ARCHITECTURE.jsonc` 和展开图中并参与适用的静态检查，但不会按 implemented body 执行。`python_stub` planned nodeset 始终作为单个 stub 执行。
