# VibeFlow 分发开发包

本模板对应 VibeFlow 0.9.0。Python 业务对象按 `vibeflow.core`、`vibeflow.targets.*` 和 `vibeflow.tooling.*` 分层导入；Python 与 JavaScript Target 及其 Application closure 完全隔离。

这个目录是给“使用内核开发业务程序的人或 AI”看的分发材料。它说明如何把程序拆成标准流程图 node、纯 `base_lib`、可选 Plugin/Capability/Host Extension 和 JSONC 配置，再走 Python Runtime 或 JavaScript/TypeScript AOT 两条公开路径。Python 普通 node 的真实 IO 受派生 effect scope 约束；JS/TS 使用 `vibeflow.plugin.v1` 扩展 hook，宿主交互通过逐调用 Capability 或 Host Extension 建模。

正式 Target 名是 `python` 与 `javascript`；TypeScript 是 JavaScript Target 支持的实现语言。

推荐分发方式：

1. 在仓库根目录运行
   `python distribution/build.py --output ../vibeflow-distribution`。
2. 构建器没有默认输出目录；它先在目标目录旁完成临时构建与校验，再发布为
   指定目录。该目录就是可复制的新项目骨架。
3. Python Runtime 项目开发 `project/nodes/`、`project/base_lib/`、
   `project/plugins/`、`project/registry.py` 和 workflow；JS/TS AOT 项目开发
   `project/nodes/`、`project/base_lib/`、`project/manifests/`、可选
   `project/web/` 和 workflow。
4. 用模板里的 `run.py` 检查、运行、审核或构建。

复制后的推荐结构：

```text
my_project/
  AGENTS.md
  README.md
  vibeflow_config.jsonc
  run.py
  kernel/
    vibeflow-kernel.zip
    MANIFEST.sha256
    README.md
    LICENSE
    docs/
    tools/
      mermaid-renderer/
    THIRD_PARTY_NOTICES.md
  project/
    vibeflow_project.jsonc
    ARCHITECTURE.jsonc
    nodes/
    base_lib/
    plugins/
    manifests/
      nodes/
      base_lib/
      data/
      capabilities/
      plugins/
      host_extensions/
    host_extensions/
    web/
    configs/
    registry.py             # Python Runtime
    package.json            # JS/TS AOT
    package-lock.json       # JS/TS AOT
  runs/
  reports/
```

开始前先区分任务类型：

- 新建项目（greenfield）可以从粗粒度 planned 流程开始，逐层审核和实现。
- 修改已有项目（existing）必须先读登记的 `ARCHITECTURE.jsonc`，沿 source 定位真实 workflow/nodeset，然后原位修改。不为审核新建平行 config，不用概念图替代真实 config。

正式架构审核使用 `python run.py review --config ... --output ...`。更完整的修改清单、人类批准门和 fail-closed 规则见复制项目根的 `AGENTS.md` 和 `kernel/docs/`。

核心原则：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局
policy。Python Runtime root 在 `vibeflow_project.jsonc` 声明 `registry`、
quality、可选 runtime 和 `architecture.documents`，由
`project/registry.py` 登记 Python node/base_lib/plugin；JS/TS AOT root 则用
`descriptors` 登记 node、base_lib、Data Schema、Capability、Plugin 和 Host Extension，用
`javascript` 指向项目自行安装并锁定的 Node.js、TypeScript 与 esbuild
工具链。`descriptors` 和 `javascript` 是合法项目字段，不应被 Python 模板规则
删除。两条路径共享显式 `pipeline.edges`、contract、nodeset、有限/永久 loop 和原生 Port 等
可移植图语义，但 Python 由 Runtime 执行，JS/TS 由 `build` 生成不依赖
Python/VibeFlow Runtime 的 ESM 或 Web 产物。完整 AOT 规则见
`docs/11_JS_TS与Web_AOT构建指南.md`。

`python run.py quality --path project` 是内置用户项目质量检查：Tooling 读取文件，对应 Target 提取语言事实，Core Quality 统一判定，Tooling 输出报告。仓库维护者使用的独立 `quality/` profiles 不进入分发包。

Plugin 与 Host Extension descriptor 路径只登记 project 可用资源。当前 workflow
在顶层 `plugins` / `host_extensions` 中选择实际使用的 ID。Planned 项进入
Architecture JSON 和图形审查，但不解析源码、不执行、不打包，也不提供
Capability；implemented 资源不能依赖 planned 资源。

登记的 `ARCHITECTURE.jsonc` 是从真实 workflow、nodeset 和资源配置确定性生成
的单文件审查视图，AI 应优先读它理解项目；改变架构时修改真实 source，再重新
生成，而不是手工编辑架构文档。Python workflow 按 id 启用当前使用的
base_lib/plugin；JS/TS workflow 按 id 启用当前使用的 Plugin 与 Host Extension；AOT
build 只纳入当前流程实际使用的 implemented descriptor 依赖闭包。
Python 普通 node 无 IO，需要真实副作用时使用语义正确的 `io` /
`document` / `data_store` 或显式 trusted 边界；JS/TS node 的宿主能力必须在
descriptor 中声明，并由同步 `runWorkflow()`、异步 `runWorkflowAsync()` 调用方或 Host Extension 注入。两条路径都不能把控制流
藏进 node import 关系。

常用命令：

```powershell
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc --check
python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py build --config project/configs/main.jsonc --target browser --profile esm-module --out-dir dist
python run.py delegate-cli --config project/configs/main.jsonc -- --input data.yaml --verbose
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
```

implemented nodeset 必须包含完整 pipeline。planned nodeset 可以无 body 占位，也可以带 body 逐步细化；body 会进入架构 JSONC 与展开图及适用静态检查，但仍不可按 implemented body 执行，`python_stub` 仍是单个 stub。

分发包中的 `sandbox/javascript/integration/` 用简单数学 node 与 TS `base_lib`
组合验证数据传递、分支/合流、nodeset、loop、同步/异步 ABI、`vibeflow.plugin.v1`、Port、Capability、Host Extension、调用隔离、
构建 profile 和非法依赖。分发后可运行：

```powershell
python sandbox/javascript/integration/run_all.py --skip-browser
```

浏览器环境可用时去掉 `--skip-browser`。沙箱从
`kernel/vibeflow-kernel.zip` 导入内核，并在临时目录安装锁定的工具链和
Puppeteer；分发目录中不会生成 `node_modules`。

CLI 让渡模式 / `delegate-cli` 把原序业务 token 作为 `cli.argv` 传入 workflow，并从唯一 `cli.exit_code` 取非 bool 整数 `0..255`。首个 `--` 可选地分隔 core/业务参数；业务直接使用真实 stdin/stdout/stderr，VibeFlow 诊断只写当次 run 的 `vibeflow.log`。授权 `SystemExit(None)` 返回 0，合法整数原样返回；框架/未授权退出错误返回 1，已知 core 参数的 argparse 错误返回 2。详细 effect scope 与授权位置见 `docs/01_Node开发规范.md`、`docs/05_BaseLib与外部依赖规范.md` 和 `docs/07_启动命令与报告.md`。`run` 与 `review` 职责不变。

`run` 会在 `runs/<run_id>/` 自动写出 `architecture.jsonc`、快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`，但不会覆盖 root 中登记的架构文档。VibeFlow 命令内部使用 bundled Mermaid CLI 渲染 SVG；普通图默认使用 `maxTextSize=200000`、`maxEdges=2000`，`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000` 并固定采用 `review-columns` SVG composer。canonical expanded SVG 只在同一父图内合并调用种类和 `type_key` 都相同的直接 nodeset 详情，父图中的调用点与连边全部保留；不同父图分别展开。external implemented node 使用 `[EXTERNAL]` 标题和 `7px` non-scaling 粗边框。Mermaid CLI/mmdc 是内部实现，不是公开审核入口。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用，并继续按调用点展开，不做局部详情去重。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG；单项诊断图可用 `python run.py svg --expand-nodesets`，正式架构审核使用 `python run.py review`。

`svg` 命令依赖 `kernel/tools/mermaid-renderer/` 中的 Mermaid CLI。首次使用前运行：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

分发包不内置 `.gitignore`，忽略策略由项目自行决定。常见建议包括忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。
