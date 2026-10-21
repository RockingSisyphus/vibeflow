# 图并发实现约束

配置示例与升级步骤统一放在[用户并发手册](../../distribution/docs/user/graph-concurrency.md)。本页描述框架实现，避免维护两份使用文档。

## Core 与公共计划

NodeCallSpec 只描述正常调用；Nodeset 和 Loop 继续复用普通子图。断路检查沿正常调度边反向分析结束可达性，所有 worker 都参加检查。分支的首个必经合流点必须是多前驱 all 汇合节点；绕过收集器的出口、先隐式合流再放单输入标记都不构成有效收集。多前驱 all 节点继续分发多路时，由两 Target 共用的 join 检查产生错误级 `GRAPH.JOIN.FORK_CONFLICT`，阻止验证和构建；不再保留 mainline review 中仅作警告的重复路径。

Workflow ABI v10 的 Block 种类限定为 workflow、nodeset、loop。解码器拒绝旧 ABI 和已删除字段，调用方必须重建产物。Core 和 Block Compiler 保存纯数据，不持有线程、Promise 或语言 callable。

## Target 调度

Python 的 [scheduler.py](../../src/vibeflow/targets/python/runtime/scheduler.py) 是唯一图协调器：先在协调线程解析输入、消费汇合信号，再提交所有独立就绪调用；完成队列仅接收真实退出后的输出或异常。节点执行时继承 contextvars，锁租约覆盖正在运行的工作。plan、block、compiled 入口共用这个协调器；生成的块只调用公共块包装函数。

JavaScript 的 [codegen_scheduler.py](../../src/vibeflow/targets/javascript/frontend/codegen_scheduler.py) 发射事件循环调度。running Map 保存已启动调用，失败后向共享 AbortController 发出停止请求，并等待剩余调用结束。同步入口保持同步 ABI，不创建 Worker。

普通调度边激活与数据传输分别处理；all 交付保留每个 envelope，按节点声明顺序排序。每轮消费 all 的入边完成信号，避免下一轮复用旧信号。

配置层从每个调用的 config 提取 `max_concurrency`，编译为 NodeCallPlan 的独立字段，业务 params 不包含它。默认值为 8；父图的全局配置不传播此额度。每次普通分发创建局部准入计数，直接目标就绪后才占名额；完成线程 join 或调用 Promise 结算后释放，随后从队列补位。Node、Nodeset 和 Loop 使用相同的调用完成边界。不存在全局线程池、SDK 管理器或额外任务子图。

多个分发同时激活同一调用时，准入检查取所有所属额度的交集，并在实际退出后一起释放；使用分发对象身份去重，同容量的两个来源仍独立计数。

## 展示

共享 `node_presentation.resolve_presentation` 从已解析的正常调度边识别普通 process 调用的多路分发和多前驱 all 回收，默认使用双圆图形；Node 声明和调用级样式继续覆盖默认值。Python、JavaScript 的 Architecture 与 Mermaid 均传入同一调用和编译事实，颜色沿用现有级联。这个展示规则不创建新的 flow_kind、运行边界或任务管理类型，也不将纯传输边当作分发；起止、Decision 和复合块保留原生形状。

## 完成与观察

Python NodeRunContext 只提供自身取消、能力访问与 trace。JavaScript NodeExecution 持有本次调用发起的 SDK 操作，包含 Promise.race 的未胜出操作。完成通知位于 finally 和能力清理之后；框架失败触发兄弟调用协作停止，仍等待不响应取消的工作实际返回。

Trace 的事件、计数和子图摘要在共用锁内更新；协调器维护调度状态。块失败回调的错误附在原始错误上，不能覆盖业务错误。Python 的执行锁释放和 JavaScript 的插件释放均发生在所属调用退出之后。

## 删除范围

独立任务图、任务注册表、控制器、结果引用、线程池补位逻辑与专用图形已删除。解析层仅保留明确的迁移错误，源码规则禁止访问已撤销的控制接口；没有兼容执行路径或备用实现。

## 维护验证

Config 解析、schema、调用配置覆写、便携计划及两 Target 的源码/AOT 必须保留相同额度。`max_concurrency` 是调度字段，不进入业务参数，不从父级 global_config 继承；同额度的不同分发也不能合并计数。相关回归位于 `tests/core/test_dispatch_config.py`、`tests/conformance/test_dispatch_concurrency.py` 与 `test_dispatch_shared_target.py`。

发布前执行两个 [graph_concurrency 沙箱](../../sandbox/README.md)：非法图必须在公开 CLI 返回错误并停止构建，不能仅检查内部 finding 是否存在；正常案例必须检查真实启动、清理、补位与收集次序，不能仅依赖最终输出。两 Target 的集成入口自动包含这些沙箱，JavaScript 同时运行 Node 和 Chromium。发行身份与构建流程见[发行装配](../maintainers/release.md)。
