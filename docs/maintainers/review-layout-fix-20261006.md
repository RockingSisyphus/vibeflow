# 正式 SVG 分片资源泄漏修复（2026-10-06）

本文供维护 Python 图形导出与共享展示资料的开发者使用。

本文保留分片资源泄漏修复时的历史证据。此处资源区采用的实现文件依赖图后来确认读者层级错误，已撤下；当前正式图使用配置所选资源的简单目录。下面的历史 SVG 与报告不作为当前资源展示规范，修复流程分片重复绘制资源的边界继续有效。

`export_mermaid(..., prepared=prepared)` 原来无条件把调用方的 `resources` 替换成 `prepared.resources`。正式展开 SVG 的主流程、父流程和叶子详情本来省略该参数，以便资源集中出现在独立区域；共享展示快照接入后，这些流程分片也绘制了 Plugin、BaseLib 等资源，造成重复内容。

修复删除这次赋值，由每次渲染的显式参数决定内容：省略、`None` 或空 mapping 绘制流程；显式资源集合绘制所选资源。`PreparedPythonPresentation` 继续提供共享编译结果、源码和声明事实。选择一个资源子集后再次绘制完整集合，不修改 Architecture，也不增加编译或实现绑定。正式主流程及 Nodeset 分片保持省略参数，独立资源区域仍消费完整 Architecture。

修复前后各包含 348 个产品源码文件，[源码清单对比](../../sandbox/python/review_layout/evidence/source-before.json)与[修复后清单](../../sandbox/python/review_layout/evidence/source-after.json)确认仅 [mermaid/__init__.py](../../src/vibeflow/tooling/application/python/presentation/mermaid/__init__.py) 变化。布局算法、方向、资源关系及运行协议沿用原实现。

## 正式入口观察

公开 SDK 夹具包含两层 Nodeset、共享定义的重复调用、Loop、BaseLib 和 compiler/runtime Plugin。四个稳定案例均经过正式 CLI；SVG 使用实际 Mermaid 渲染器和浏览器观察。

| 案例 ID | 入口 | 修复前 | 修复后 |
|---|---|---|---|
| `layout.review.nested_repeat_loop` | `review` | 流程分片及最终 SVG 出现资源泄漏 | 通过 |
| `layout.expanded_svg.nested_repeat_loop` | `export-svg --expand-nodesets` | 流程分片及最终 SVG 出现资源泄漏 | 通过 |
| `layout.mermaid.explicit_resources` | 普通 Mermaid 导出 | 通过 | 通过 |
| `layout.ordinary_svg.explicit_resources` | 普通折叠 SVG 导出 | 通过 | 通过 |

[修复前报告](../../sandbox/python/review_layout/before.json)为 2/4，[修复后报告](../../sandbox/python/review_layout/after.json)为 4/4，观察错误均为 0。两个修复前展开入口的 CLI 退出码均为 0；沙箱通过真实分片及 SVG 内容识别错误，而非依赖命令是否成功。

展开观察保留 8 个 Mermaid 分片、3 列及 2 个嵌套面板。主流程和有子图的父流程为 TD，叶子分片为 LR；父流程在左，子面板在右纵向堆叠，重复调用保留各调用 ID。资源区的 Architecture 保存 8 个资源、7 个文件、25 个关系。自动检查覆盖分片方向、区域隔离、面板排列、代表性叶子节点的实际 X 方向及样式；整体节点、连边和其他叶子排列另经截图目视核对。

代表产物：[展开 SVG](../../sandbox/python/review_layout/evidence/after/layout.review.nested_repeat_loop/graph.svg)、[Architecture](../../sandbox/python/review_layout/evidence/after/layout.review.nested_repeat_loop/ARCHITECTURE.jsonc)、[浏览器资料](../../sandbox/python/review_layout/evidence/after/layout.review.nested_repeat_loop/browser.json)、[截图](../../sandbox/python/review_layout/evidence/after/layout.review.nested_repeat_loop/graph.png)。逐个资源关系或每个叶子的浏览器几何并非逐一自动验收项。

## 回归与验收状态

[新增测试](../../tests/tooling/test_review_fragment_resources.py)覆盖共享定义、父子分片、显式全量与子集、空选择，以及 `default/review-columns` 两种文本布局。11 项新增测试与 6 项原共享准备测试通过；另有 17 项原布局、资源与运行 SVG 产物测试通过，共 34 项、无跳过。证据为[目标测试日志](../../sandbox/python/review_layout/evidence/unit-after.log)和[原布局日志](../../sandbox/python/review_layout/evidence/strict-layout-after.log)。[性能沙箱](../../sandbox/python/review_layout/evidence/performance-after.json.gz)的 57 项检查通过。

`tools/verify_project.py --full` 已加入 `review-layout-sandbox`，缺失案例、渲染失败、浏览器观察错误及期待不匹配均使该步骤失败。运行与证据说明见[沙箱文档](../../sandbox/python/review_layout/README.md)。

全量 pytest 为 1963/1963，Python 集成沙箱为 138/138，独立质量检查器的 46 项测试通过，仓库检查为 0 errors/0 warnings。完整日志与两包验收汇总见 [0.15.1 修复构建记录](releases/0.15.1/review-layout-fix-verification.json)。本轮执行上述检查、新布局及性能沙箱，未重新执行 `verify_project.py --full` 的全部 16 个阶段。

两个 0.15.1 分发包均已重建，每包实际解出内核后通过 79 项隔离回归及 4 项布局 CLI/浏览器验收。348 个内核文件与修复后源码逐项一致，文档、AI 提示词与清单通过[独立发行审核](releases/0.15.1/review-layout-package-audit.json)。初始两个包保留在 `archive/history/0.15.1-initial-20261006/`，原发行记录继续对应初始哈希。

验证期间的临时目录配额、Chromium socket 路径过长、文档索引遗漏及两个提前终止的集成会话均保留原记录。修正环境与索引后分别完整重跑；最终集成进程退出码为 0，138 项结果及图形发布审计全部通过。
