# 用户项目 SVG 的展示边界修正

本次删除了将资源定义与源码审核资料直接投影到用户项目 SVG 的实现。正式图服务于使用 VibeFlow 分发包开发的项目：它展示真实 Workflow 调用、配置实际使用的资源和 Nodeset 详情。Core/Target 内部的资源定义与检查实现不是这张图的展示对象。

## 原因与旧版依据

基线 `f169429` 的 Python `mermaid/review_fragments.py::_resource_mermaid` 为每组资源生成 `flowchart LR`：分类父节点直接连接配置选择的条目。`review_svg.py::_resource_columns` 按 Plugin、BaseLib、Host 分列；JS 的 `review.py::_resource_records/_resource_mermaid` 使用当前构建的选择记录，另保留 Capability 目录。数据来自 ConfigResources 或当前 workflow 构建资料，没有从 Catalog 枚举定义目录。

正式展开图按列从左到右排列。主流程纵向；含有子 Nodeset 的父流程纵向，子详情位于其右侧上下排列；叶子 Nodeset 横向。这些布局约定继续使用。Nodeset 的 `expand` 只控制展示，健康检查和执行仍处理实际内部实现。

错误路径在多文件资源阶段的 `1febc99` 引入：Python `review_svg.py` 用 `render_resource_graph(architecture["implementation_graph"])` 替换原来的资源目录。随后把它拆为多个 resource section，仍保留实现文件、导入、贡献和跨区 reference。因此分区并未解决展示层级错误。

例如，用户选择 `demo.math` 时，目录应该只多一项库。错误版本又增加该库的入口、支撑文件、归属和引用端点。`demo.math` 是沙箱用户项目的库；错误不是其名称，而是把检查资料当成了流程图里的对象。统一 SDK 注册、多文件归属和 Rule/Ruleset 都不要求这样渲染。

## 已删除与保留

删除整个 `tooling/presentation/resource_mermaid.py`；删除 Architecture 的资源分区、reference 和附加 rule_graph 投影；删除 Python/JS 的所有实现图到 SVG/Mermaid 接入，以及 `show_rules` 和 CLI `--show-rules`。不是通过默认关闭保留旧路径。

用户图恢复简单资源目录：父节点连接本次选择的 Plugin 包、BaseLib、Host；Node 位于实际业务调用处。同一包的 compiler/runtime 不再成为多个插件目录条目。颜色、图形、图标、状态与使用处样式继续应用到实际条目。

`implementation_graph` 的 resources/files/relations 保留为项目审核与源码查询事实，供 Architecture JSONC 及规范性验证使用，没有 SVG 消费者。独立的 `review-rules` 继续用于显式规则查询。原生执行、源码所有权检查、延迟绑定边界与检查会话复用不变。

## 回归与历史

原分区方案的机器报告和截图冻结保存，现行期待另存。原 `--show-rules` 案例保持 ID，迁为明确拒绝已删除参数，核对退出码 2 和无产物发布。

- Python：`sandbox/python/review_layout/user-layer-after.json` 与 `sandbox/python/resource_sections/user-layer-after.json`。
- JS：`sandbox/javascript/resource_sections/user-view-after.json` 与 `user-view-browser.json`。
- 测试对图中出现 Node 类型目录、规则定义、源码文件或 reference 作反向断言；Python prepared 渲染不能请求源码 Architecture，也不能新增绑定、编译或规则执行。
- 展示与修改沙箱继续检查用户调用及目录条目的所有公开形状、颜色、图标和实际浏览器几何。

本次只修改源码、回归与文档源文件，未构建或覆盖分发包。

最终验证：全量 pytest **2,041 项通过**；资源展示与修改的真实 CLI／浏览器沙箱 **150/150**（展示 103、修改 47）；Python 布局 4/4、折叠与资源入口 14/14、JS 对应入口 14/14；性能回归 57/57。独立仓库质量工具测试 46 项通过，`quality/run.py --profile all --format json` 返回零错误、零警告。

固定源码及各机器报告见 [验证汇总](user-svg-boundary-verification-20261006.json)。本轮未执行 `verify_project.py --full` 的发行验收，也没有以源码测试替代分发包验收。
