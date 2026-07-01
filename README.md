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

下面是 integration sandbox 中一个完整示例导出的 SVG 流程图。

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
4. 让 AI 先按 `AGENTS.md` 生成 planned 流程图，确认结构后再逐步实现业务 node、base_lib、plugin 和 JSONC config。

发布包根目录会带有 `AGENTS.md`。支持项目指令的 AI 工具会自动读取它，并理解：

- 哪些目录可以改。
- 哪些内核文件不能改。
- 如何新增 node、nodeset、plugin。
- 如何运行 validate、run、quality、diagram 命令。
- 运行前必须满足哪些健康检查。
- 如何先设计 planned nodeset，导出流程图给人审核，再逐层实现。

你不需要先理解完整内核源码，也不需要手工配置复杂工程。把发布包当成一个带规则的 AI 开发工作目录即可。

## 发布包中的典型结构 📦

```text
project/
  nodes/          # 业务 node
  base_lib/       # 纯函数 helper
  plugins/        # 可选策略和运行插件
  configs/        # JSONC 流程配置
  registry.py     # 节点注册
kernel/
  vibeflow/       # VibeFlow 内核副本，通常不改
AGENTS.md         # 给 AI 的项目规则
run.py            # 项目入口
```

常用命令形态：

```bash
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py quality --path project
```

## AI 开发工作流 🛠️

```text
描述需求
  -> AI 抽象成粗粒度标准流程图
  -> 用 planned nodeset 写入 JSONC
  -> 导出 Mermaid 或 SVG 给人审核
  -> 审核通过后逐层展开 nodeset
  -> 实现 node/base_lib/plugin/config
  -> validate / quality / run
  -> 继续迭代
```

重大结构变更也走同一模式：先 planned、先出图、先审核，再实现。尚未确定的部分保留为 `status: "planned"`，VibeFlow 会允许它用于设计审查，但不会让它伪装成可运行程序。

VibeFlow 不阻止你 vibe coding。它只是让每一轮 vibe 都必须回到可检查的结构里。

## 原理简述 ⚙️

VibeFlow 的核心是一个严格的流程图运行时：node 负责局部纯计算，JSONC config 负责声明控制流，compiler 负责把流程编译成可执行图，health checker 负责在运行前拦截结构漂移和契约错误。

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

这让 AI 写出的代码不只是“能跑”，还必须能放回一张可审查的流程图里。

### 显式流程边

程序控制流只来自 JSONC 配置里的 `pipeline.edges`。

`requires` / `provides` 只是数据契约，不会被偷偷推导成控制流。这样可以避免项目在多轮 AI 修改后出现隐式路径和隐藏依赖。

### 小 node 和纯逻辑

业务 node 默认必须是纯函数：

- 不读写文件。
- 不访问网络。
- 不连数据库。
- 不启动浏览器或外部进程。
- 不读取环境变量。
- 不直接调用其他 node。

真实 IO 通过 `io`、`data_store`、`document` 等流程图节点建模；第三方或外部维护代码用 `NodeInfo.external=True` 标记。

### 运行前健康检查

VibeFlow 会在运行前检查：

- 节点元数据是否完整。
- 输入输出契约是否清晰。
- 流程是否从 start 可达并能到达 end。
- cycle 是否经过 decision。
- node 是否违反纯函数和结构规则。
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
- `docs/current_implementation_status.md`：当前实现状态。
- `docs/strict_kernel_design.md`：严格流程图设计。
- `docs/developer_guide.md`：使用者开发指南。
- `docs/kernel_development_guide.md`：VibeFlow 自身维护指南。
- `distribution/kernel_development_pack/`：发布包模板。

## 项目状态 🚧

VibeFlow 仍在快速演进中。当前重点是把 AI 协同开发中的结构纪律、流程图表达、运行前检查和发布包体验打磨稳定。

如果你相信未来的软件会越来越多由人和 AI 一起维护，那么项目需要的不只是更强的生成能力，还需要更硬的结构边界。

VibeFlow 就是这层边界。
