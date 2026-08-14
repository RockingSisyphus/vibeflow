# 执行模型

## 控制与数据

显式 edge 分别携带 schedule 与 transfer 角色。调度决定节点是否激活和 join readiness；传递决定 envelope 是否进入目标 inbox。`requires` / `provides` 不生成隐式控制边。

入口数据只进入可达调用的 inbox，输出 envelope 沿已激活 transfer edge 传播。最终结果仅保留 pipeline 公共 outputs 和运行元数据。

## Block、Nodeset 与 Loop

顶层 workflow、Nodeset 和 Loop body 都编译为有限 BlockPlan。Nodeset dependency 无递归，静态嵌套深度由 root Runtime 配置限制。Loop 是唯一重复执行语义，迭代次数不累计静态嵌套深度。

Python 可按 plan、block 或 compiled 模式执行；JavaScript emitter 将同一公共计划生成流程专用 ESM。两个 Target 都必须保留路由、合流、输入输出和任务所有权语义。

## 异步所有权

TaskPlan 明确 immediate、suspend、deferred、detached 和 `result_key` 的所有权。需要 join 的结果必须存在可证明的 scheduled consumer path；未归属后台任务在支持静态分析的 Target 中被拒绝。

## 副作用与执行锁

Core 根据 Node 类型事实派生 effect scope。`global_state` 表达易失 ambient state 或 runtime dispatch；`external=True` 和 Plugin 是 trusted 边界。

命名 `execution_lock` 表达冲突域。Target 的 execution lease 管理等待、获取、可重入嵌套和释放；异常与取消路径通过 `try/finally` 释放。锁只协调执行，不授予副作用能力或事务恢复。

## Trace 与执行证据

Runtime trace 保存顶层和限定路径执行顺序、Node 运行、edge 激活、Block/Loop 边界、锁事件和失败信息。工作流执行探针从这些事实中选择可证明的 coverage 项，不推导业务正确性。
