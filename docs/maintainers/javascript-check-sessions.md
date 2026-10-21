# JS/TS 单次检查会话

正式命令通过私有 `DriverScope` 拥有分析 driver、规则会话与资源退出栈。嵌套的 Target 阶段借用当前作用域；直接调用 Target 检查入口时创建自己的作用域。作用域随一次命令结束释放，不跨 workflow、进程或后续命令保存缓存。

`DriverSession` 使用有界 JSONL 请求传递分析资料，保留每个请求 180 秒超时。AOT 构建仍有独立入口。driver 以源码快照、后端、编译选项和有效根集合区分 Program，并复用同一源码及符号投影的函数指标和调用图。不同规则参数和资源权限仍独立判断；源码或分析上下文变化时重新分析。

沙箱中的 Program 构造、函数指标和调用图计数用于断言重复分析消失。这些计数观测 VibeFlow 服务入口，不代表 TypeScript 或 Babel 内部的每一次解析。不同有效根集合产生多个 Program 属于正常行为。耗时对照使用新进程、单 worker，各运行三次；墙钟时间作为本机观察。

Rule 和 compiler hook 使用有限图快照：定义保留一次，Nodeset 与 Loop 关系引用定义。hook 保持只读快照、注释及合法 void 返回语义。Host 先解析选择和依赖闭包，审查、预览、Architecture 与构建消费同一闭包；支撑源码不创建新的 Host 实例。

退出时逐项释放规则、生命周期、worker、driver、管道与临时资源。释放失败不会中断后续清理；已有主错误保留为根因，释放错误进入其 details。正常退出也报告释放错误。这里约束框架的清理流程，不承诺中止任意用户代码中永久阻塞的 dispose。

源码结构 Rule 消费声明归属、实际导入边和入口符号使用资料。每个 workflow、每个所属资源分别判定权限。插件声明可以引用其贡献资源；生命周期实现引用贡献资源不自动得到同样权限。普通未登记代码仍使用原有项目结构检查。

Target 分别提取入口引用和模块初始化引用。与入口同文件的插件声明承担其模块初始化检查，入口按自己的实际引用检查；没有该声明归属的实现同时检查两者。类型引用、别名，以及初始化时实际调用的本地方法和构造器均保留导入位置；未调用的本地方法不会凭空成为入口依赖。另一 workflow 的声明不会改变当前 workflow 的权限。

功能、性能对照及发行包隔离复验的命令和报告格式见[资源与审查适配回归](../../tests/fixtures/adaptation_regressions/README.md)。

## Prepared fact views

`build/fact_views.py` adapts complete source/declaration inputs to the shared
`targets/shared/facts.py` store. Node local facts remain distinct from the native
background. Graph inputs retain finite definitions, effective scope and
boundaries. Views are captured before repeated calls, with project quality facts
prepared only when the selected implementations require them. The session reuses
that prepared derivation; it does not serialize all sources for every call.

`build/analysis_service.py` owns driver analysis/result reuse. Its request keys
include package root and Node command. `quality/diagnostics.py` converts findings.
`build/rule_wire.py` only encodes already-prepared facts and never starts analysis.
Native rules use these service interfaces instead of importing orchestration
helpers from `rule_session.py`.

Source result identities combine the relevant view, responsibility and actual
native binding or worker/module/export binding. Temporary handler closures are
not implementation identities. Worker sessions distinguish changed bindings;
command cleanup clears facts, analysis and rule caches after closing resources.
Core continues to distinguish phase, parameters and input records. Program keys
and module-initialization semantic facts retain their existing behavior.

The formal CLI performance fixture is
`tests/fixtures/javascript/review_performance/run_all.py`. It records actual
driver requests, Program builds, worker evaluations and view captures. A Node
loader observer counts Program cache misses without changing cache decisions.
One/four repetitions of the same eight-node, four-library Nodeset must not add
driver requests, Program builds or source-worker evaluations. Compare three fresh
processes on the same machine; wall-clock results are observations, not portable
pass/fail thresholds.

Common declarations, Node catalogs and execution configuration are captured once
before resource iteration. Each resource derives only its source/ownership and
local-quality parts from that immutable background. These derivations reuse
Core-owned readonly values rather than re-encoding/freezing the full catalog.
Unused driver prefetch objects stay in the analysis service, outside fact views.
