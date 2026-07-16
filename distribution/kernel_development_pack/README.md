# VibeFlow 分发开发包

这个目录是给“使用内核开发业务程序的人或 AI”看的分发材料。它不解释内核内部实现，只说明如何把程序拆成标准流程图 node、纯 `base_lib`、可选 plugin 和 JSONC 配置，并通过内核强制健康检查后运行。普通 node 保持纯函数；真实 IO 只能在由 `flow_kind` / `external` 派生的受控 effect scope 中使用。

推荐分发方式：

1. 在仓库根目录运行 `python build_distribution.py`。
2. 复制生成的 `vibeflow_distribution/` 作为新项目骨架。
3. 在新项目里开发 `project/nodes/`、`project/base_lib/`、`project/plugins/` 和 `project/configs/*.jsonc`。
4. 用模板里的 `run.py` 启动检查、运行和图形导出。

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
    configs/
    registry.py
  runs/
  reports/
```

开始前先区分任务类型：

- 新建项目（greenfield）可以从粗粒度 planned 流程开始，逐层审核和实现。
- 修改已有项目（existing）必须先读登记的 `ARCHITECTURE.jsonc`，沿 source 定位真实 workflow/nodeset，然后原位修改。不为审核新建平行 config，不用概念图替代真实 config。

正式架构审核使用 `python run.py review --config ... --output ...`。更完整的修改清单、人类批准门和 fail-closed 规则见复制项目根的 `AGENTS.md` 和 `kernel/docs/`。

核心原则：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局 policy；每个 root 的 `vibeflow_project.jsonc` 声明 registry、quality、可选 runtime 参数和 `architecture.documents`。runtime 可配置每个 Runtime 的 `async_max_workers`、detached 收尾的 `async_flush_timeout` 和 nodeset/loop body 的 `nodeset_max_depth`。登记的 `ARCHITECTURE.jsonc` 是从真实 workflow/nodeset/registry 确定性生成的单文件审查视图，AI 应优先读它理解项目；改变架构时修改真实 workflow config 或相关 nodeset，再重新生成，而不是手工编辑架构文档。同一个 `project/registry.py` 声明可用 node、base_lib 和 plugin。每个 workflow config 再按 id 声明本流程实际使用的 base_lib/plugin，审查产物只展示实际引用的资源。`quality.structure` 默认用 warning/error 双阈值治理 root 代码布局，允许 root 总文件数增长到 120，但单个代码目录超过 16 个 `.py` 会失败，促使 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。业务开发者只写小型 node、纯 helper、必要插件和 JSONC 拓扑配置；普通 node 无 IO，需要真实副作用时必须使用语义正确的 `io` / `document` / `data_store` 或显式 trusted 边界；控制流只写在显式 `pipeline.edges` 中；运行前由内核自动健康检查，检查不过不执行。

常用命令：

```powershell
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc --check
python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py delegate-cli --config project/configs/main.jsonc -- --input data.yaml --verbose
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
```

implemented nodeset 必须包含完整 pipeline。planned nodeset 可以无 body 占位，也可以带 body 逐步细化；body 会进入架构 JSONC 与展开图及适用静态检查，但仍不可按 implemented body 执行，`python_stub` 仍是单个 stub。

CLI 让渡模式 / `delegate-cli` 把原序业务 token 作为 `cli.argv` 传入 workflow，并从唯一 `cli.exit_code` 取非 bool 整数 `0..255`。首个 `--` 可选地分隔 core/业务参数；业务直接使用真实 stdin/stdout/stderr，VibeFlow 诊断只写当次 run 的 `vibeflow.log`。授权 `SystemExit(None)` 返回 0，合法整数原样返回；框架/未授权退出错误返回 1，已知 core 参数的 argparse 错误返回 2。详细 effect scope 与授权位置见 `docs/01_Node开发规范.md`、`docs/05_BaseLib与外部依赖规范.md` 和 `docs/07_启动命令与报告.md`。`run` 与 `review` 职责不变。

`run` 会在 `runs/<run_id>/` 自动写出 `architecture.jsonc`、快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`，但不会覆盖 root 中登记的架构文档。VibeFlow 命令内部使用 bundled Mermaid CLI 渲染 SVG；普通图默认使用 `maxTextSize=200000`、`maxEdges=2000`，`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000` 并固定采用 `review-columns` SVG composer。Mermaid CLI/mmdc 是内部实现，不是公开审核入口。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG；单项诊断图可用 `python run.py svg --expand-nodesets`，正式架构审核使用 `python run.py review`。

`svg` 命令依赖 `kernel/tools/mermaid-renderer/` 中的 Mermaid CLI。首次使用前运行：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

分发包不内置 `.gitignore`，忽略策略由项目自行决定。常见建议包括忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。
