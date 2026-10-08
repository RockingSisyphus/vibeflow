# 执行模型

## 控制与数据

显式 edge 分别携带 schedule 与 transfer 角色。调度决定节点是否激活和 join readiness；传递决定 envelope 是否进入目标 inbox。`requires` / `provides` 不生成隐式控制边。

入口数据只进入可达调用的 inbox，输出 envelope 沿已激活 transfer edge 传播。最终结果仅保留 pipeline 公共 outputs 和运行元数据。

执行前按 canonical `pipeline.inputs` 检查公共输入：未声明键失败，`required=true` 的键必须存在，`required=false` 的键可缺失。键存在而值为 null 不等于缺失；后续类型检查仍独立生效。缺省、null、整数或字符串形式的 required 在解析时失败。输入合同失败时业务 Node 不执行。嵌套 Nodeset 的输入映射及 Loop carry/body 输入同样遵守声明，不通过过滤未知键补偿配置错误。

## Block、Nodeset 与 Loop

顶层 workflow、Nodeset 和 Loop body 都编译为有限 BlockPlan。Nodeset dependency 无递归；静态嵌套深度的审查限制由选中的 Ruleset 参数决定，root Runtime 配置提供内置规则的默认参数，显式调用参数和 overrides 优先。未选择该规则时不添加独立的深度门禁。Loop 是唯一重复执行语义，迭代次数不累计静态嵌套深度。

Python 可按 plan、block 或 compiled 模式执行；JavaScript emitter 将同一公共计划生成流程专用 ESM。两个 Target 都必须保留路由、合流、输入输出和任务所有权语义。

## 异步所有权

TaskPlan 明确 immediate、suspend、deferred、detached 和 `result_key` 的所有权。需要 join 的结果必须存在可证明的 scheduled consumer path；未归属后台任务在支持静态分析的 Target 中被拒绝。

## 副作用与执行锁

effect scope 来自选中 Rule 的有效 `vibeflow.effect_policy.v1` 资料，不由 flow_kind、external 或插件身份推导权限。多个规则的资料分别保留；摘要出现不同约束时显示 `mixed`，调用级规则保留各实际调用的结果，未提供效果约束时显示 `unconstrained`。planned 实现没有完成源码检查，显示 `unavailable`。`global_state` 仍表达易失 ambient state 或 runtime dispatch，`external=True` 标识外部实现；这些原生身份不自动跳过选中的规则。

实际 Rule 参数只接受 none、terminal、python_io、global_state、trusted 五个 scope。terminal 仅允许终端效果；python_io 在各 Target 允许相应一般 I/O；global_state 允许资源或模块状态，但禁止修改 builtin、原型及宿主关键状态；trusted 不增加权限。放宽 scope 按效果类别判定，不关闭整个检查 topic。导入 policy 的显式禁止独立生效，python_io 不能覆盖它。JavaScript 保留其已有时间、随机数检查，本轮没有为 Python 增加对应禁令。

命名 `execution_lock` 表达冲突域。Target 的 execution lease 管理等待、获取、可重入嵌套和释放；异常与取消路径通过 `try/finally` 释放。锁只协调执行，不授予副作用能力或事务恢复。

## 检查与执行入口

固定插件入口及直接导入先初始化以提供资源定义。import 检查在后续绑定前执行：已加载源码接受诊断，尚未加载的延迟实现及闭包在检查失败后保持未加载。static 用于 quality、validate、review 和构建审查；Python run 执行选定运行入口，JS AOT 产物按原生计划执行业务。新领域 Ruleset 未声明 run/import 时，这两个入口为空。

规则结果记录健康判断，解析、符号绑定和执行计划提供原生成功或失败事实；两者分别汇入正式报告。资源查询和 review-rules 加载声明，框架不调用检查函数、业务入口或生命周期工厂。装配职责见[系统架构的插件装配与多文件源码](system-architecture.md#插件装配与多文件源码)。

source 范围的规则只能按本次检查内明确的源码快照、声明、参数和类型化输入复用，公共视图不暴露某一个业务调用的可变配置；call 范围逐调用执行。规则允许同时返回诊断和有效资料，依赖只消费完成且满足输出契约的资料。

## 宿主与多文件实现

JS/TS Host 由一个 createHost 工厂创建一个具有 capabilities/start/stop 的实例。入口及 implementation_files 中的支撑实现共同服务该实例；订阅、FIFO、取消、计时器、IO 与回执保留即时处理时机。会话状态在工厂内建立或显式传给支撑对象，各 createWorkflowHost 调用持有独立状态。Host dependencies 表达其他宿主实例依赖，base_libs 表达独立辅助库引用。

AOT 打包实际运行依赖，TS 类型在构建时擦除；Rule 和 compiler 专用代码留在检查与编译环境。多文件登记提供完整审查资料，文件是否初始化仍由真实运行引用决定。

## Trace 与执行证据

Runtime trace 保存顶层和限定路径执行顺序、Node 运行、edge 激活、Block/Loop 边界、锁事件和失败信息。工作流执行探针从这些事实中选择可证明的 coverage 项，不推导业务正确性。

## 运行观测

Core 提供纯数据的运行状态记录与 JSON 信息快照契约。Python Target 持有本次运行的上下文、双日志及定时文件写入；Tooling 在声明装配前建立观测范围，使加载和健康检查失败也产生最终状态。CLI 接管本进程的输出描述符，嵌入式 Runtime 使用上下文标准流。

JS emitter 包含可移植的信息缓存和状态回调。Node 构建另附文件适配器，用 AsyncLocalStorage 关联控制台输出，使用独立状态线程及原子替换写入 JSON。浏览器使用 onStatus，由宿主接入存储。Host 会话拥有一个观测范围，原生多次工作流调用复用它，正常停止后发布最终状态；调度、Capability 和生命周期协议保持原有语义。

新运行清空缓存，状态变化和结束立即发布，定时更新读取最新缓存。SDK 只允许业务修改 info，state/error/updated_at 来自内核。用户接口见[运行日志与状态接口](../user/runtime-observation.md)。
