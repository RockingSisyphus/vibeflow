# JS/TS 单次检查会话

正式命令通过私有 `DriverScope` 拥有分析 driver、规则会话与资源退出栈。嵌套的 Target 阶段借用当前作用域；直接调用 Target 检查入口时创建自己的作用域。作用域随一次命令结束释放，不跨 workflow、进程或后续命令保存缓存。

`DriverSession` 使用有界 JSONL 请求传递分析资料，保留每个请求 180 秒超时。AOT 构建仍有独立入口。driver 以源码快照、后端、编译选项和有效根集合区分 Program，只保留当前编译环境，并复用同一源码及符号投影的函数指标和调用图。不同规则参数和资源权限仍独立判断；源码或分析上下文变化时重新分析。

性能回归使用固定工程的完整构建/运行成本与正常子进程资源观察，并检查源码编辑、恢复及跨工程隔离后的结果。内部 Program、解析次数及缓存身份不作为测试判据。

Rule 和 compiler hook 使用有限图快照：定义保留一次，Nodeset 与 Loop 关系引用定义。hook 保持只读快照、注释及合法 void 返回语义。Host 先解析选择和依赖闭包，审查、预览、Architecture 与构建消费同一闭包；支撑源码不创建新的 Host 实例。

退出时逐项释放规则、生命周期、worker、driver、管道与临时资源。释放失败不会中断后续清理；已有主错误保留为根因，释放错误进入其 details。正常退出也报告释放错误。这里约束框架的清理流程，不承诺中止任意用户代码中永久阻塞的 dispose。

源码结构 Rule 消费声明归属、实际导入边和入口符号使用资料。每个 workflow、每个所属资源分别判定权限。插件声明可以引用其贡献资源；生命周期实现引用贡献资源不自动得到同样权限。普通未登记代码仍使用原有项目结构检查。

Target 分别提取入口引用和模块初始化引用。与入口同文件的插件声明承担其模块初始化检查，入口按自己的实际引用检查；没有该声明归属的实现同时检查两者。类型引用、别名，以及初始化时实际调用的本地方法和构造器均保留导入位置；未调用的本地方法不会凭空成为入口依赖。另一 workflow 的声明不会改变当前 workflow 的权限。

功能、性能和隔离交付的统一入口见[开发与验证](development.md)，逐域判据见[测试覆盖](../../sandbox/TEST_COVERAGE.md)。

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

Common declarations, Node catalogs and execution configuration are captured once
before resource iteration. Each resource derives only its source/ownership and
local-quality parts from that immutable background. These derivations reuse
Core-owned readonly values rather than re-encoding/freezing the full catalog.
Unused driver prefetch objects stay in the analysis service, outside fact views.

## 编译环境的生命周期

[`analysis_program.mjs`](../../src/vibeflow/targets/javascript/resources/analysis_program.mjs) 的 `AnalysisSession.current` 拥有唯一当前环境及释放函数，替代多项 Program 缓存和累积释放列表。driver 请求循环串行执行，无需新增锁、队列、LRU 容量或内存阈值配置。

- 连续请求的 package root、后端版本、根文件集合、编译选项、workflow 临时目录相同，且本地源码/覆盖快照未变时，借用当前环境。同一节点的多条规则继续复用编译资料，各请求仍独立判定权限、参数与分析主题。
- 上下文或源码内容变化时，先断开当前引用并释放旧环境，再创建新环境。释放包括 Snapshot、API、临时配置及旧对象引用；已释放环境不能被再次命中。一个集合被其他集合替换后，再次请求它允许重新构造。
- 环境创建、源码资料提取失败时清理部分创建的资源。独立调用 `analysisProgram()` 返回自有释放函数；会话中的请求借用环境，请求结束时的 `dispose()` 不销毁仍可复用的当前环境。正式审查的诊断提取也包含在请求的 `try/finally` 内。
- 命令结束时关闭最后一个环境，并清空函数指标与调用图结果缓存。重建完整编译环境不会清空这些小型结果缓存，也不会清空上层已完成的规则/质量事实缓存。

这处理了 TypeScript 7.0.2 中每个 API 对应一个 `tsc --api` 服务所造成的内存倍增：旧逻辑为不同文件集合保留完整 API、Snapshot 与 Program 到命令末尾。当前逻辑限制同时持有的完整分析环境数量；单个大型环境和普通结果缓存仍会随输入规模占用内存。普通 Python Target 使用进程内语法树等资料，不经过这一 JS Target 路径，Core 的规则调度也不拥有这些编译服务。

[`sdk_loader.mjs`](../../src/vibeflow/targets/javascript/resources/sdk_loader.mjs) 的打包回调另有短期 API，并在自己的 `finally` 释放。因此“只保留当前分析环境”不等于整个构建命令只能观察到一个 TypeScript 子进程。自定义 Rule worker 的源码服务也有独立生命周期；此处不将本次分析驱动的验证扩大为所有插件实现的内存证明。

## 内存与行为复验

`tests/e2e/test_performance.py` 使用固定真实工程，从正式 CLI 构建到普通宿主运行，记录墙钟、CPU 及正常子进程 RSS。相同工程、源码编辑、另一工程及恢复后均有独立预期；数据写入 JUnit property，供同环境对比，不是跨机器速度保证。

源码诊断与权限通过 test_source_policies.py、test_rules.py、test_resources.py 的合法/非法工程对照确认，清理和取消由真实应用的结果、日志与收据确认。不得恢复模块加载改写、隐藏 Program 探针或内部调用计数。大型工程若出现实际资源或耗时退化，先测正常业务链，再根据证据复核生命周期设计；不预先增加长期 API 池或通用缓存管理器。

SDK 的方法、`run` 缩写及 `run: run` 绑定共用现有实现声明解析，调用链检查从实际函数进入，不能把未找到 `declaration.run` 的情况当作空调用链。`test_quality.py` 通过正常 SDK 项目和 CLI 验证三种写法的合法、warning、error 和恢复结果；不读内部调用图来生成答案。
