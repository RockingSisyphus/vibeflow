# 执行模型

## 控制与数据

显式 edge 分别携带 schedule 与 transfer 角色。调度决定节点是否激活和 join readiness；传递决定 envelope 是否进入目标 inbox。`requires` / `provides` 不生成隐式控制边。

入口数据只进入可达调用的 inbox，输出 envelope 沿已激活 transfer edge 传播。最终结果仅保留 pipeline 公共 outputs 和运行元数据。

## Block、Nodeset 与 Loop

顶层 workflow、Nodeset 和 Loop body 都编译为有限 BlockPlan。Nodeset dependency 无递归；静态嵌套深度的审查限制由选中的 Ruleset 参数决定，root Runtime 配置提供内置规则的默认参数，显式调用参数和 overrides 优先。未选择该规则时不添加独立的深度门禁。Loop 是唯一重复执行语义，迭代次数不累计静态嵌套深度。

Python 可按 plan、block 或 compiled 模式执行；JavaScript emitter 将同一公共计划生成流程专用 ESM。两个 Target 都必须保留路由、合流、输入输出和任务所有权语义。

## 异步所有权

TaskPlan 明确 immediate、suspend、deferred、detached 和 `result_key` 的所有权。需要 join 的结果必须存在可证明的 scheduled consumer path；未归属后台任务在支持静态分析的 Target 中被拒绝。

## 副作用与执行锁

effect scope 来自选中 Rule 的有效 `vibeflow.effect_policy.v1` 资料，不由 flow_kind、external 或插件身份推导权限。多个规则的资料分别保留；摘要出现不同约束时显示 `mixed`，调用级规则保留各实际调用的结果，未提供效果约束时显示 `unconstrained`。planned 实现没有完成源码检查，显示 `unavailable`。`global_state` 仍表达易失 ambient state 或 runtime dispatch，`external=True` 标识外部实现；这些原生身份不自动跳过选中的规则。

命名 `execution_lock` 表达冲突域。Target 的 execution lease 管理等待、获取、可重入嵌套和释放；异常与取消路径通过 `try/finally` 释放。锁只协调执行，不授予副作用能力或事务恢复。

## 检查与执行入口

import 规则在业务实现导入前执行；static 用于 quality、validate、review 和源码构建审查；run 只执行明确选择的运行入口。规则判断与原生解析、符号绑定、契约和执行计划的成功事实分开：空规则选择不创造 Target 尚不支持的执行能力。新领域规则未声明 run/import 时不会自动扩大这两个入口。

source 范围的规则只能按本次检查内明确的源码快照、声明、参数和类型化输入复用，公共视图不暴露某一个业务调用的可变配置；call 范围逐调用执行。规则允许同时返回诊断和有效资料，依赖只消费完成且满足输出契约的资料。

## Trace 与执行证据

Runtime trace 保存顶层和限定路径执行顺序、Node 运行、edge 激活、Block/Loop 边界、锁事件和失败信息。工作流执行探针从这些事实中选择可证明的 coverage 项，不推导业务正确性。
