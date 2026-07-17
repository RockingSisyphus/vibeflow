# VibeFlow

[English](README.en.md)

> 让 AI 开发的项目，不至于变成一座难以维护的屎山。

VibeFlow 强制 AI 先计划好程序的大概架构再进行开发，并自动根据程序**真实代码逻辑**生成可直接查阅的标准程序流程图，以便开发者直观了解程序各部分的真实结构逻辑，而不是根据 AI 可能失真的表述来猜测。VibeFlow强制 AI 遵守高内聚、低耦合、小文件、小函数、显式流程边和可检查契约。AI 仍然可以高速开发，但每一轮修改都必须回到可视化、可校验、可运行的流程图里。

## 为什么需要 VibeFlow 🧯

LLM 很擅长快速写代码，也很擅长在多轮修改后悄悄制造这些问题：

- 一个函数越长越长，最后没人敢动。
- 新功能绕过旧结构，隐式依赖越来越多。
- 修 bug 变成局部补丁，根因留在系统里。
- 项目架构逐渐混乱臃肿，最后ai自己也弄不清。

最终代码还能跑，但结构已经无法审查，功能难以加入，bug没人能修。

VibeFlow 的愿景是把这些风险前移：在 AI 写代码之前就给它一套可执行的项目纪律，让结构、契约、流程和产物都能被机器检查。

## 一句话 🧭

VibeFlow 把项目约束成一张可运行、可检查、可视化的标准流程图。

```text
terminal start -> io input -> process -> decision -> process -> io output -> terminal end
```

AI 仍然负责写业务代码，但它必须按流程图开发：每个节点小而清晰，控制流只来自配置，运行前必须通过健康检查。

## 效果展示 ✨

下面是 integration sandbox 中一个完整示例导出的 SVG 流程图。整个 AI 开发过程中，开发者随时可以查看 `reports/` 目录下生成的最新流程图来了解项目当前的逻辑结构，以用最小的精力随时保持对项目整体状态的了解。

![VibeFlow comprehensive flowchart](docs/assets/comprehensive_flowchart.svg)

## 适合谁 👥

- 使用 OpenCode、Codex、Claude Code 等 vibe coding 工具长期开发项目的人。
- 想让 AI 参与开发，但不想让项目结构失控的人。
- 希望业务流程能被 Mermaid / ASCII / SVG 图审查的人。
- 希望每次运行前都有自动结构检查、契约检查和质量检查的人。

## 使用方式 🚀

VibeFlow 面向发布包使用。

1. 到 GitHub Releases 下载最新发布包。
2. 解压到你的工作目录。
3. 用任意 vibe coding 软件在该目录创建或打开项目，例如 OpenCode、Codex、Claude Code。
4. 让 AI 先按 `AGENTS.md` 判断任务类型：已有项目先读登记的架构文档并原位修改真实 workflow/nodeset；空白项目才从粗粒度 planned 流程图开始。
5. 用 `python run.py review` 生成正式架构审核产物；如果你要求“审核后再实现”，AI 必须等待你在后续消息中明确批准。

发布包根目录会带有 `AGENTS.md`。支持项目指令的 AI 工具会自动读取它，并理解：

- 哪些目录可以改。
- 哪些内核文件不能改。
- 如何新增 node、nodeset、plugin。
- 如何运行 validate、run、quality、diagram 命令。
- 如何先读并更新不可手工编辑的 `ARCHITECTURE.jsonc`。
- 运行前必须满足哪些健康检查。
- 如何区分空白项目与已有项目，并在真实 source 上完成修改。
- 如何用 `review` 生成正式审核图，在人类明确批准后再实现。
- 如何用 CLI 让渡模式 / `delegate-cli` 把 workflow 当成普通业务命令行程序。

你不需要先理解完整内核源码，也不需要手工配置复杂工程。把发布包当成一个带规则的 AI 开发工作目录即可。

## 发布包中的典型结构 📦

```text
AGENTS.md         # 给 AI 的项目规则，可按项目定制
README.md        # 项目说明，可按项目定制
run.py            # 项目入口
kernel/
  vibeflow-kernel.zip
  MANIFEST.sha256
  README.md
  docs/           # 内核说明，可读但不作为项目内容修改
  tools/
    mermaid-renderer/
  THIRD_PARTY_NOTICES.md
project/
  ARCHITECTURE.jsonc # 由真实 source 生成的单文件架构审查视图
  nodes/          # 业务 node
  base_lib/       # 纯函数 helper
  plugins/        # 可选策略和运行插件
  configs/        # JSONC 流程配置
  registry.py     # 注册 node/base_lib/plugin 可用资源
runs/
reports/
```

常用命令形态：

```bash
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
python run.py quality --path project
```

每个 root 可以在 `vibeflow_project.jsonc` 的 `architecture.documents` 中登记 workflow 与架构文档。生成文件用固定注释明确标记为 generated、non-executable，不用可手改的状态属性伪装；AI 应优先读文档理解项目架构。要改变架构，应修改真实 workflow config 或相关 nodeset，必要时再修改 registry metadata/config schema，然后重新生成；不要手工编辑架构文档。已登记文档缺失、陈旧或被手工改写时，`validate` / `run` 会拒绝继续并给出源文件位置与修复命令。

`review` 是正式架构审核入口：它检查登记关系和现有图、更新并复核 canonical `ARCHITECTURE.jsonc`、执行 workspace validate，再生成并检查 expanded `review-columns` SVG。任一步失败都不会用旧 SVG、手写图或直接调用 mmdc 补位，也不会把失败产物发布到目标路径。`PASS` 或 `CONCERNS` 只表示机器审核完成；如果任务约定“审核后再实现”，仍需等待人类在后续消息中明确批准。

CLI 让渡模式 / `delegate-cli` 用于面向最终用户的普通业务 CLI。首个 `--` 可选地分隔 core 与业务参数；未被 core 消费的 token 按原序作为 `cli.argv` 进入 workflow，图必须从唯一 `cli.exit_code` 输出非 bool 整数 `0..255`。业务直接使用真实 stdin/stdout/stderr，VibeFlow 不捕获、重写或添加 JSON/换行；内核诊断写入当次 run 的 `vibeflow.log`，不记录 argv 原文或业务流。只有 `io` / `document` / `data_store` node 和 runtime plugin 可发出授权 `SystemExit`；正常/授权退出返回 `0..255`，框架失败返回 1，已知 core 参数的 argparse 错误返回 2。`delegate-cli` 不改变 `run` 的通用执行职责或 `review` 的架构审核职责。

同一份 root 配置还可设置 `runtime.async_max_workers`（默认 4）、`runtime.async_flush_timeout`（默认 `null`）和 `runtime.nodeset_max_depth`（默认 4）。线程数控制每个 Runtime 的独立线程池；普通 nodeset 与 `loop.body` 共用深度限制，循环迭代次数不累计。线程数和深度不提供 CLI 参数。

`run` 会在 `runs/<run_id>/` 自动写出当次 `architecture.jsonc`、快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`；它不会覆盖 root 中登记的文档。`svg` 命令内部会为 bundled Mermaid CLI 传入放大的渲染配置；Mermaid CLI/mmdc 是内核实现细节，不是公开的审核入口。普通图默认 `maxTextSize=200000`，`--expand-nodesets` 默认 `maxTextSize=500000`。
展开 SVG 会固定使用确定性的 `review-columns` composer：主流程保持在左侧，右侧依次展示当前 workflow 实际启用的 plugins/base_lib 和按顶层调用顺序排列的展开 nodeset。nodeset 详情使用递归 detail-panel：叶子 nodeset 横向展示；包含子 nodeset 的父图保持 collapsed call-site 和原始连边，右侧按调用顺序纵向展示直接子 nodeset。审查图默认把单个片段显示宽度限制为 `3200px`，可用 `--review-fragment-max-width` 调整。
`graph.expanded.mmd` 只是 Mermaid 源码调试产物，不要直接用 Mermaid CLI/mmdc 转成 SVG。正式架构审核必须使用 `run.py review`；`run.py svg --expand-nodesets` 只保留为单项导出或诊断入口。
SVG 渲染不要求系统预装 Google Chrome；正常 `npm install` 后会优先使用 Puppeteer 自己安装/缓存的浏览器。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。
在发布包中首次使用 SVG 前，到 `kernel/tools/mermaid-renderer/` 执行 `npm install`。发布包不内置 `.gitignore`，项目可以自行决定是否忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/` 等产物。

## AI 开发工作流 🛠️

先判定任务类型，再进入对应路径：

```text
修改已有项目
  -> 读已登记的 ARCHITECTURE.jsonc
  -> 定位文档指向的真实 workflow / nodeset source
  -> 列出复用 / 修改 / 删除 / 新增清单
  -> 在原 config 和 nodeset 上作最小修改
  -> run.py review -> 人类后续明确批准 -> 实现 -> validate / quality / run

新建空白项目
  -> 抽象粗粒度标准流程图
  -> 用 planned nodeset 写入真实 JSONC
  -> run.py review -> 人类后续明确批准
  -> 逐层实现 node / base_lib / plugin / config
  -> validate / quality / run
```

已有 workflow 默认原位修改；不得用平行 review config、手写 Mermaid、概念图或笼统差异图代替真实 config 的审核。只有空白项目或人类明确批准整体重构时，才从新的粗粒度 planned 拓扑开始。planned nodeset 可以无 body 占位，也可以带 body 逐步细化；body 会进入单文件架构文档、展开图和适用的静态检查，但不会按 implemented body 执行。`python_stub` nodeset 仍只作为单个 stub，implemented nodeset 则必须有完整 pipeline。

VibeFlow 不阻止你 vibe coding。它只是让每一轮 vibe 都必须回到可检查的结构里。

## 原理简述 ⚙️

VibeFlow 的核心是一个严格的流程图运行时：普通 node 负责局部纯计算，具有显式语义的 node/plugin 在派生 effect scope 内执行真实副作用，JSONC config 负责声明控制流，compiler 负责把流程编译成可执行图，health checker 负责在运行前拦截结构漂移和契约错误。

它把“项目架构”从口头约定变成机器可以执行的检查。

## 核心能力 🧩

### 标准流程图约束

每个 node 都必须声明标准 `flow_kind`：

- `terminal`：开始 / 结束。
- `process`：普通处理。
- `decision`：判断 / 路由。
- `io`：输入 / 输出动作。
- `predefined`：预定义过程 / nodeset。
- `data_store`：数据存储请求或引用。
- `document`：文档生成或文档结构。
- `preparation`：准备 / 初始化。

`flow_kind` 与 `external` 一起决定内核派生的 `effect_scope`：普通 implemented node 和 planned `python_stub` 为 `none`；`flow_kind=io` 为 `terminal`，开放真实标准流、`print` / `input` / `argparse`；`document` / `data_store` 为 `python_io`，开放文件、环境、网络、数据库、subprocess 和终端；任意 `external=True` node 和 plugin 为最高优先级 `trusted`。图形 `flow_kind=terminal` 仍是 `none`，不等于权限档位 `terminal`。

### 显式流程边

程序控制流只来自 JSONC 配置里的 `pipeline.edges`。

`requires` / `provides` 只是数据契约，不会被偷偷推导成控制流或图上的理论数据边。这样可以避免项目在多轮 AI 修改后出现隐式路径和隐藏依赖。

Health 会在显式 edge 中推断同步主线、data bypass 和 async 相关边：主线 edge 负责调度并在 SVG/Mermaid 加粗，data bypass 只投递数据不触发目标并显示虚线，async edge 连接显式 async node/nodeset。

配置调用点使用 `id` 和 `type_used`：`type_used` 指向 Python node 的 `NodeInfo.type_key`、独立 nodeset JSONC 的 `type_key` 或系统类型。数据契约使用严格结构化写法：`provides` 声明唯一 `key`、逻辑 `type` 和 `display_name`，`requires` 按 `type`、`cardinality` 和 `display_name` 消费。运行时通过 node inbox / edge payload 传递 envelope，不支持跨多跳从全局 Context 偷读早期输出；最终结果只保留 `pipeline.outputs` 声明的内容。

### 小 node 和显式副作用

普通 `effect_scope=none` 业务 node 必须是纯函数：

- 不读写文件。
- 不访问网络。
- 不连数据库。
- 不启动浏览器或外部进程。
- 不读取环境变量。
- 不直接调用其他 node。

`io` node 可使用真实终端流，`data_store` / `document` node 可使用 Python IO。`external=True` 和 plugin 是 `trusted` 边界；`external=True` 确实会显式绕过普通 IO/purity 限制，因此只能用于真正外部维护或受信任实现。这些类别仍必须遵守契约、拓扑、输出和 trace，也不能仅为获得权限而伪造 `flow_kind`。effectful / external node 的 `CONTRACT.examples` 只做结构检查，不执行。

### 运行前健康检查

VibeFlow 会在运行前检查：

- 节点元数据是否完整。
- 输入输出契约是否清晰。
- 流程是否从 start 可达并能到达 end。
- 同步分支是否能解释为 mainline、data bypass、async 或显式 `join_policy: "all"` 汇合。
- 普通 graph / nodeset 内部是否存在显式环路；真实循环必须使用一等 while loop。
- node 是否违反其派生 effect scope 和结构规则。
- 配置、插件、nodeset 是否破坏项目边界。

检查失败就拒绝运行，并输出可追踪的原因。

### 可视化产物

同一份配置可以导出：

- Mermaid 流程图。
- ASCII 终端流程图。
- SVG 图形文件。

这让人类可以审查整体结构，也让 AI 更容易理解当前项目边界。

## 仓库文档 📚

- `docs/kernel_target_vision.md`：目标愿景。
- `docs/developer_guide.md`：使用者开发指南。
- `docs/kernel_development_guide.md`：VibeFlow 自身维护指南。
- `docs/strict_flowchart_kernel_redesign.md`、`docs/11_*.md`、`docs/12_*.md`、`docs/13_*.md`：历史设计记录和阶段计划，不作为当前公开接口规范。
- `distribution/kernel_development_pack/`：发布包模板。

## 许可证 📄

VibeFlow 使用 GNU Affero General Public License v3.0（AGPLv3）授权。详见 `LICENSE`。

## 项目状态 🚧

VibeFlow 仍在快速演进中。当前重点是把 AI 协同开发中的结构纪律、流程图表达、运行前检查、训练/批处理运行性能和发布包体验打磨稳定。

如果你相信未来的软件会越来越多由人和 AI 一起维护，那么项目需要的不只是更强的生成能力，还需要更硬的结构边界。

VibeFlow 就是这层边界。
