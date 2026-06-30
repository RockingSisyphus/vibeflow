# Paperflow Kernel 反馈复核

> 历史说明：本文是 flowchart 内核重构前的 Paperflow 反馈审查记录。文中的 `boundary`、显式 loop、`max_iterations` 等术语反映当时的内核模型和 Paperflow 项目状态，不代表当前 `topology-kernel` 的公开 API。当前模型以标准 `flow_kind`、显式 `pipeline.edges`、terminal start/end、decision cycle 和 `NodeInfo.external=True` 为准。

本文记录对 `/home/rockingsisyphus/projects/paperflow` 的一次外部开发体验反馈复核。分析分两阶段：

1. 先仅基于 paperflow 项目事实复核反馈是否成立。
2. 再阅读当前 kernel 项目文档，按 kernel 的初心和开发理念重新评估是否应修改 kernel。

## 第一阶段：基于 paperflow 的初步结论

### 结论

开发者反馈总体成立。kernel 在 paperflow 中已经有效约束了结构性问题，但仍放过了一些需要语义理解的职责边界问题。当前更值得改进的是 kernel 的“引导与提示能力”，而不是把所有建议都升级成硬错误。

### 已核对事实

- `python3 run.py quality --path project` 结果为 `PASS`，`errors=0`，`warnings=0`。
- `python3 run.py validate --config project/configs/paperflow_offline_demo.jsonc` 结果为 `PASS`，`errors=[]`，`warnings=[]`。
- 抽样测试 `tests/test_artifact_tools.py`、`tests/test_fulltext_http_boundary.py`、`tests/test_fulltext_browser_boundary.py` 通过。
- `project/registry.py` 中 `_register_fulltext_nodes()` 确实注册了多项 `literature.*` node，包括 `literature.source_rows`、`literature.merge_dedupe`、`literature.match_terms`、`literature.rank_records`、`literature.summary`。这不是运行错误，但从维护角度看是分组职责错误。
- `project/boundaries.py` 中 `_execute_http_route()` 调用 `_select_http_provider()`，`project/browser_boundary.py` 中 `_execute_browser_route()` 调用 `_select_browser_provider()`。这类逻辑规模不大，但属于“boundary 执行 IO 时顺手做决策”。
- `project/base_lib/artifact_tools.py` 同时包含 PDF 文档汇总、项目链接发现、repo URL 解析、repo audit、最终 paperflow summary。它们仍是纯逻辑，不违反当前规则，但文件职责已经偏宽。
- `project/configs/paperflow_nodesets.jsonc` 与 `project/configs/paperflow_offline_demo.jsonc` 复制了同一批 nodeset 定义，说明当前配置复用能力不足。
- `docs/migration_steps/09_artifact_links_repos_memo.md` 明确记录了 duplicate AST warning、`urllib.parse` 在 base_lib 中被禁、contract semantics/examples 补全等返工。

### 初步判断

1. **kernel 起效了。**

   paperflow 的代码确实被迫形成了 `nodes/`、`base_lib/`、`boundary`、`configs/nodesets` 的分层。副作用基本集中在 boundary，纯逻辑基本位于 node 或 base_lib。开发 memo 中也能看到 kernel 对未声明输出、重复逻辑、base_lib import、契约完整性等问题的即时反馈。

2. **kernel 目前主要防守“结构性坏味道”。**

   当前规则能检查动态输出 key、未声明契约、IO import、文件大小、重复 AST、boundary provides 等问题。但它无法判断“注册函数名称和注册 node namespace 是否一致”“一个 base_lib 文件是否聚合了过多业务领域”“boundary 中 provider selection 是否已经变成业务策略”。

3. **paperflow 没有严重滥用 boundary/base_lib。**

   当前问题是轻度职责漂移，不是架构失控。Provider selection 在 boundary 中只是少量逻辑；`artifact_tools.py` 虽宽，但仍是纯函数；真实 IO 没有明显泄漏进 node/base_lib。

4. **部分规则已经产生形状噪声。**

   duplicate AST warning 曾迫使开发者调整实现形态。该规则的方向正确，但对小型 wrapper node 过于机械时，会鼓励无意义结构差异。

### 第一阶段建议

按优先级，初步建议如下：

1. **增加 registry namespace consistency warning。**

   例如 `_register_fulltext_nodes()` 注册 `literature.*` 时提示 warning。该规则应先作为 maintainability warning，而不是 hard error，因为旧项目迁移时可能存在临时聚合。

2. **支持 nodeset include/import。**

   这是 paperflow 中最明确的配置组织痛点。缺少 include 会迫使 runnable config 复制 nodeset 大段定义，增加漂移风险。

3. **调整 duplicate AST 规则。**

   对简单 node wrapper、固定 `run_pure` 形态、仅字段名不同的适配 node，应该允许通过标准模式或降级为更温和提示，避免开发者为消除 warning 写结构噪声。

4. **增加 boundary decision-logic smell warning。**

   当 boundary 中出现 `_select_*provider`、`rank`、`score`、`audit`、`plan` 等命名时给 warning。此规则应提示“策略可能应前移到 node/base_lib”，不能简单禁止，因为 boundary 内仍需要做少量执行层选择和错误分类。

5. **为 base_lib 提供纯标准库白名单机制。**

   `urllib.parse` 的 URL 解析在纯逻辑中是合理依赖。完全禁止 `urllib` 会诱导手写 URL parsing，反而降低可靠性。更合适的是允许 `urllib.parse`，继续禁止 `urllib.request`。

6. **评估 boundary lifecycle 的中间注入点。**

   paperflow 的自然拓扑是 search plan -> boundary execution -> normalize/summary。目前 boundary 主要 before/after run，表达多段 IO DAG 时不自然。可以考虑显式 IO node 或 boundary stage hook，但这会改变 kernel 表达模型，需在阅读 kernel 文档后再定优先级。

## 第二阶段：按 kernel 初心重新审视

### 已阅读的 kernel 文档要点

- `docs/kernel_target_vision.md` 明确说明 kernel 面向人机协同和 LLM 深度参与开发，目标不是让开发更自由，而是用硬性规则限制自由度，防止巨型模块、隐式依赖、副作用污染和架构不可审计。
- 同一文档把 `node`、`nodeset`、`pipeline`、`boundary`、`base_lib`、`policy`、`plugin` 定义为一等概念，并要求治理策略可解释、可分层、可降级、有来源。
- `docs/strict_kernel_design.md` 要求凡是违反高内聚、低耦合、纯函数、原子化、显式拓扑和边界隔离目标的情况，都应由健康检查给出硬失败或显式警告。
- `docs/current_implementation_status.md` 说明当前实现已经覆盖纯度、契约、nodeset、boundary、运行产物、插件和质量检查，但仍未形成完整的语义和架构漂移检查。
- `docs/node_health_quality_migration_progress.md` 给出一个重要边界：`quality-check` 的仓库结构规则不直接移植到 node 健康检查；node 健康检查只接收与运行安全、纯度、base_lib 可靠性直接相关的能力，结构维护规则更适合留在 quality-check 或项目级结构健康检查中。

### 复核后的总判断

应该修改 kernel，但修改方向应保持“核心绝对规则少而硬，语义/结构气味多用 warning、policy 和 plugin 表达”。

paperflow 的反馈没有推翻 kernel 方向，反而证明了 kernel 的基本假设：LLM 开发确实需要机器规则防止隐式 IO、契约漂移、动态输出和无约束拓扑。但 paperflow 也暴露出下一阶段治理重点：当前硬规则足够拦住结构性失控，却还不能很好提示“职责放错位置”和“配置复用困难”。

因此不建议把所有 paperflow 反馈升级为 hard error。更合适的是：

- 对明显影响可维护性的通用能力，进入 kernel 核心 warning。
- 对领域语义强、误报风险高的能力，放入 project policy/plugin。
- 对仅 paperflow 局部组织不佳的问题，先作为 paperflow 重构，不改 kernel。

## 最终建议

### 需要修改 kernel 核心

1. **支持 nodeset include/import。**

   这是最明确、最符合 kernel 初心的核心改动。kernel 强调“程序结构必须由配置显式组织”，而 nodeset 是复杂功能组合的一等机制。如果 runnable config 必须复制大段 nodeset 定义，配置本身会成为新的维护风险。建议增加 JSONC 级别的 nodeset 引用机制，例如：

   - `include_nodesets: ["paperflow_nodesets.jsonc"]`
   - 或 `nodeset_imports: [{"path": "...", "names": ["paperflow.catalog"]}]`

   该能力应保留可审计性：健康报告输出展开后的 nodeset 来源、文件路径、名称冲突和版本冲突。

2. **把纯标准库 allowlist 做到更细粒度。**

   当前禁止整个 `urllib` 会让 `urllib.parse` 这种纯解析能力也不可用，paperflow 因此手写 URL parsing。按 kernel 初心，规则应防止副作用污染，而不是逼开发者重写可靠标准库。建议把 import policy 从 root 级别扩展到模块/成员级别：

   - 允许 `urllib.parse`
   - 继续禁止 `urllib.request`
   - 对 `pathlib.Path` 这类既可纯拼接也可 IO 的 API，继续通过调用级 AST 检查区分

3. **优化 duplicate AST 的治理方式。**

   duplicate AST 规则符合“防止重复逻辑和补丁式扩写”的目标，但 paperflow 证明它对简单 wrapper node 容易产生形状噪声。建议改为：

   - 对 `run_pure` 只有取输入、调用 base_lib、返回固定 provides 的 wrapper，默认降为 info 或合并同类提示。
   - 对非 wrapper 的重复 helper、重复分支、重复转换逻辑继续 warning。
   - finding 中说明“是否为标准 wrapper 模式”，避免开发者通过无意义临时变量规避 fingerprint。

4. **增加 boundary decision-logic smell warning。**

   kernel 文档明确要求 node 输出结构化请求，boundary 执行副作用并把结果写回。paperflow 中 `_select_http_provider()` 和 `_select_browser_provider()` 还很轻，但代表了 boundary 可能逐渐承担策略的方向。建议在 boundary 健康检查中增加非阻断 warning：

   - 命中 `_select_*provider`、`rank`、`score`、`audit`、`plan`、`strategy` 等命名时提示复核。
   - 只提示“可能应迁移到 node/base_lib”，不默认失败。
   - 允许项目 policy 调整关键词或降级/关闭。

5. **增加 registry namespace consistency warning。**

   这项也适合进核心 warning，因为它不依赖 paperflow 业务知识，只检查注册函数/文件/类目和 type key namespace 的一致性。例如 `_register_fulltext_nodes()` 注册 `literature.*`，应提示可能的职责分组错误。实现上应谨慎：

   - 先检查显式函数名 `_register_<namespace>_nodes` 与注册 key 前缀。
   - 不作为 hard error，因为迁移期和聚合注册器可能有合理例外。
   - 支持 policy/plugin 声明允许的跨 namespace 注册。

6. **改进 boundary lifecycle 表达，但不要急于引入“IO node”。**

   paperflow 的 search plan -> boundary -> normalize 诉求真实存在。不过 kernel 文档已经设计了 `before_iteration` / `after_iteration` 与显式有界环路，理论上可以表达多轮外部交互。优先建议：

   - 改善文档和示例，展示如何用 loop + boundary iteration 表达 plan/request/result/normalize。
   - 如果仍不够，再考虑多 boundary stage 或 named boundary hooks。
   - 暂不建议把 boundary 做成普通 node，否则会冲击“node 必须纯函数”的核心边界。

### 更适合 policy/plugin 的改动

1. **领域化 boundary 关键词。**

   `provider`、`audit`、`score` 在不同项目中的语义差异很大。核心可以提供默认弱 warning，但项目应能用 policy/plugin 维护自己的词表。

2. **base_lib 领域聚合检查。**

   `artifact_tools.py` 过宽在 paperflow 中成立，但“PDF/repo/summary 是否是同一领域”不能只靠 kernel 判断。核心质量工具可以提供文件函数数、公共 API 数、prefix cluster 等信号；具体拆分建议应放 project policy/plugin 或人工审查。

3. **注册分组严格性。**

   核心只做 namespace mismatch warning。是否禁止跨组注册，应由项目 policy 决定。

### 不建议修改 kernel 核心的部分

1. **不应因 paperflow 直接把 provider selection 禁止在 boundary。**

   boundary 执行真实 IO 时，仍需要少量执行层选择、错误分类、fallback 和资源路径判断。硬禁会造成误伤。正确方向是 smell warning + 结构化请求约定。

2. **不应把所有语义职责判断做成 hard error。**

   kernel 初心是机器化架构纪律，但它也有 policy 分层和可降级规则。语义职责边界天然有灰度，应先用 warning 建立反馈闭环。

3. **不应为了消除 duplicate AST warning 鼓励代码形态变化。**

   如果规则让开发者写出额外临时变量、`list(...)` 或其他无意义差异，说明规则需要理解 wrapper 模式，而不是要求开发者继续迁就 fingerprint。

### paperflow 自身应先做的重构

- 把 `project/registry.py` 中 `literature.*` 注册移回 `_register_literature_nodes()`。
- 将 `project/base_lib/artifact_tools.py` 拆为 `pdf_tools.py`、`repo_tools.py`、`summary_tools.py` 或类似结构。
- 将 HTTP/browser provider selection 尽量前移到 `fulltext.plan_provider_routes` 或 base_lib 纯逻辑中，boundary 只执行 route 上指定的 provider。
- 在有 include/import 支持前，尽量只维护一个 nodeset 定义来源，减少 config 复制。

## 最终结论

需要修改 kernel，且优先级如下：

1. **P0：nodeset include/import。**
2. **P1：细粒度纯标准库 allowlist，尤其允许 `urllib.parse`、继续禁止 `urllib.request`。**
3. **P1：duplicate AST wrapper 模式识别，降低形状噪声。**
4. **P2：boundary decision-logic smell warning。**
5. **P2：registry namespace consistency warning。**
6. **P3：boundary lifecycle 示例和必要时的 named stage 扩展。**

这些改动符合 kernel 初心：继续保持 node 纯函数、拓扑显式、boundary 隔离和健康报告可审计，同时把治理从“机械形状检查”推进到“可解释的职责边界提示”。其中 P0/P1 是核心体验和可靠性问题，应进入 kernel；P2/P3 更适合先以 warning、policy/plugin 和示例演进，避免把语义判断过早硬编码。
