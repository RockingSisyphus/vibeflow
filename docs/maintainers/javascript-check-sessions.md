# JS/TS 单次检查会话

正式命令通过私有 `DriverScope` 拥有分析 driver、规则会话与资源退出栈。嵌套的 Target 阶段借用当前作用域；直接调用 Target 检查入口时创建自己的作用域。作用域随一次命令结束释放，不跨 workflow、进程或后续命令保存缓存。

`DriverSession` 使用有界 JSONL 请求传递分析资料，保留每个请求 180 秒超时。AOT 构建仍有独立入口。driver 以源码快照、后端、编译选项和有效根集合区分 Program，只保留当前编译环境，并复用同一源码及符号投影的函数指标和调用图。不同规则参数和资源权限仍独立判断；源码或分析上下文变化时重新分析。

沙箱分别观察当前编译环境的创建/释放、函数指标与调用图的结果复用。这些计数观测 VibeFlow 服务入口，不代表 TypeScript 内部的每一次解析。连续请求复用当前环境；A → B → A 的文件集合切换允许重新创建 A，不能用“全命令内每个集合只创建一次”要求框架保留所有完整环境。性能沙箱的耗时对照使用新进程，各运行三次；墙钟时间作为本机观察。

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

## 编译环境的生命周期

[`analysis_program.mjs`](../../src/vibeflow/targets/javascript/resources/analysis_program.mjs) 的 `AnalysisSession.current` 拥有唯一当前环境及释放函数，替代多项 Program 缓存和累积释放列表。driver 请求循环串行执行，无需新增锁、队列、LRU 容量或内存阈值配置。

- 连续请求的 package root、后端版本、根文件集合、编译选项、workflow 临时目录相同，且本地源码/覆盖快照未变时，借用当前环境。同一节点的多条规则继续复用编译资料，各请求仍独立判定权限、参数与分析主题。
- 上下文或源码内容变化时，先断开当前引用并释放旧环境，再创建新环境。释放包括 Snapshot、API、临时配置及旧对象引用；已释放环境不能被再次命中。一个集合被其他集合替换后，再次请求它允许重新构造。
- 环境创建、源码资料提取失败时清理部分创建的资源。独立调用 `analysisProgram()` 返回自有释放函数；会话中的请求借用环境，请求结束时的 `dispose()` 不销毁仍可复用的当前环境。正式审查的诊断提取也包含在请求的 `try/finally` 内。
- 命令结束时关闭最后一个环境，并清空函数指标与调用图结果缓存。重建完整编译环境不会清空这些小型结果缓存，也不会清空上层已完成的规则/质量事实缓存。

这处理了 TypeScript 7.0.2 中每个 API 对应一个 `tsc --api` 服务所造成的内存倍增：旧逻辑为不同文件集合保留完整 API、Snapshot 与 Program 到命令末尾。当前逻辑限制同时持有的完整分析环境数量；单个大型环境和普通结果缓存仍会随输入规模占用内存。普通 Python Target 使用进程内语法树等资料，不经过这一 JS Target 路径，Core 的规则调度也不拥有这些编译服务。

[`sdk_loader.mjs`](../../src/vibeflow/targets/javascript/resources/sdk_loader.mjs) 的打包回调另有短期 API，并在自己的 `finally` 释放。因此“只保留当前分析环境”不等于整个构建命令只能观察到一个 TypeScript 子进程。自定义 Rule worker 的源码服务也有独立生命周期；此处不将本次分析驱动的验证扩大为所有插件实现的内存证明。

## 内存与行为复验

复现入口为 [`memory_probe.py`](../../tests/fixtures/javascript/review_performance/memory_probe.py)，方法见[夹具说明](../../tests/fixtures/javascript/review_performance/README.md)。它直接运行当前源码的真实 build/review，固定顺序空节点图，仅改变节点数和源码文件分组。两侧选用默认 `vibeflow.process` 规则，关闭可选 project/root 治理检查以隔离变量。登记的 Architecture 预先生成，不计入测量。

2026-10-25 本机环境为 Linux、Python 3.13.13、Node v24.18.0、TypeScript 7.0.2、esbuild 0.28.1。JS build 使用 `--target node --profile single-esm`，Python 使用 `python-package`；review 使用默认 HTML 预览，不请求可选 SVG。验证对象为当前工作区源码，未替换或独立验收发行包。

正式修改后的结果与修改前诊断对照如下，单元格为 `tsc --api` 峰值数量 / RSS 合计峰值：

| 节点 / 文件 | 修改前 build | 修改后 build | 修改前 review | 修改后 review |
| --- | --- | --- | --- | --- |
| 8 / 1 | 3 / 327.6 MiB | 2 / 234.5 MiB | 1 / 224.2 MiB | 1 / 217.9 MiB |
| 8 / 8 | 10 / 1023.5 MiB | 2 / 261.5 MiB | 9 / 1024.1 MiB | 1 / 260.6 MiB |
| 12 / 12 | 14 / 1434.3 MiB | 2 / 291.7 MiB | 13 / 1406.7 MiB | 1 / 266.1 MiB |

当前 JS/Python 12 次真实 CLI 均 PASS，6 次 review 均发布 HTML 预览，采样见到的编译服务在命令后均已退出。Python 三组 build 为 37.2、37.4、38.9 MiB，review 为 34.5、35.0、36.0 MiB，均未出现 TypeScript 编译服务。

RSS 为 CLI 及全部后代进程的合计采样峰值，可能重复计算共享页，不是独占内存；采样每轮休眠 30 ms，间隔还包括进程遍历开销，可能漏掉短暂进程或瞬时峰值。每格一次运行，不用于跨机器内存或速度门禁。

本轮验证边界：

- `test_analysis_session.py` 与 `strict_aot_toolchain.py`：24 passed。新增真实 driver 进程观察覆盖连续相同请求复用同一服务、同文件内容变化重新创建、切换 8 个文件并返回先前文件时不保留旧服务。
- `test_aot_core.py`、`strict_aot_project_build.py` 与 `test_javascript_review_publish.py`：121 passed、1 skipped。跳过项需要未安装的 Mermaid SVG renderer；真实默认 HTML review 已在上表验收。两批合计 145 passed、1 skipped，未运行仓库全量回归。
- S02 资源分析夹具的 validate 与 quality-check 两例均 PASS，测得最多一个活动分析环境、结束后零活动环境，函数指标与调用图无重复提取；节点权限仍独立检查。
- 复杂性能夹具的三组配置各跑三个新进程，全部通过。8 节点 / 4 BaseLib 的 Nodeset 从 1 次变为 4 次调用后，每次均为 77 个 driver 请求、24 次 Program 构造、8 次自定义 source Rule 执行。相应墙钟中位数为 8.124 s 和 8.767 s，仅作本机观察，不宣称跨机器速度保证。
- 随后的 JS 相关整批为 1188 passed、0 failed、0 skipped；锁定 Mermaid 11.17.2 的图形补验为 147 passed、0 failed、0 skipped，JS integration 为 51 passed、0 failed、0 skipped。本地 1.4.3 双 profile 包已构建并解压复验；包内 8 节点 / 8 文件 review 的编译服务峰值为 1、RSS 合计峰值为 252.9 MiB，结束后零编译服务残留。新增 JS 模板目录声明问题及其 34 项回归见[发行说明](release.md)。
- 临时工程、测量输出、测试缓存、隔离资源副本与本轮临时图形依赖均已清理；未进行 GitHub 发布或业务部署。整批 JS 验证不能代表完整仓库或远端 CI 验收。

复杂项目使用既有 shared BaseLib、真实自定义 source Rule、重复 Nodeset 的性能夹具复验；行为回归覆盖源码变化、权限隔离、正常及异常释放，以及真实构建/预览发布。完整环境的短期切换不能改变规则结果；若大型项目出现 A → B → A 切换导致显著重复构造，再根据实际请求记录复核复用策略，不预先叠加长期 API 池或通用缓存管理器。
