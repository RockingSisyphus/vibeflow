# Python 检查会话与展示资料

本文供维护源码分析、规则适配和图形导出的开发者使用。公开插件 SDK、Workflow 配置和 ABI 沿用现有契约。

## 一次命令的资料流

正式入口先装配选中的插件和声明，再建立源码与规则资料，执行所选入口，最后生成编译结果。`PythonCheckSession` 属于这一次检查或运行，入口通过 `try/finally` 释放它。独立注册器调用使用临时会话。

会话复用源码解析、导入闭包、符号和归属索引、实现投影、指标、规则图，以及具备相同事实视图的源码规则结果。事实视图包含声明、源码内容、插件配置、策略、加载状态和额外资料；规则的有效参数、输入 records 和实际 handler 也参与结果复用。未知可变额外对象会获得独立视图。

`import/static/run` 保持各自的入口与缓存。调用级规则仍接收每个真实调用的 owner、路径和参数。源码规则复用后保留诊断的真实状态、records 和全部调用关联；绑定判断读取有效结果，缓存命中时也会拒绝错误或资料缺失。BaseLib 按自己的声明和实际导入闭包检查。

源码结果缓存使用 records 的 JSON 数据身份。包含 frozen dataclass、frozenset 等 Python 原生资料的输入仍按原类型传递给规则，每次分别检查；其 JSON 输出投影不能代表 consumer 能观察到的实际类型。

Record 冻结、可缓存性判断和内部内容摘要分别复用已完成的对象转换。共享 DAG 保留共享关系，循环仍被拒绝。缓存键和诊断去重使用内容摘要，包括端口、类型、参数、上下文及 handler；最终 JSON 继续输出普通值树。审查成本与输出 JSON 的展开成本分别计量。

`quality` 可以在一次命令内检查多个 Workflow 并扫描项目源码。它仅在这些步骤间共享以源码路径和内容为键的语法解析结果；每个 Workflow 的声明、权限、插件参数、加载状态和规则执行缓存仍分别建立、释放。下一次命令重新建立解析缓存。语法错误保留原来的消息、行号和列号，源码内容变化后重新解析。

补充源码查询返回自己的分析结果和加载状态。它可以借用解析缓存，但不改写当前 workflow 发布的源码快照、调用关联或加载状态。只有装配当前有效调用及实际绑定后的发布步骤更新活动资料。

compiler 阶段保存一次编译产物：创建、before、after、dispose 各执行一次，沿用既有阶段顺序。后续规则只更新自己拥有的派生事实，保留 after 对编译产物的合法修改。检查、inspect、展示及 checked Runtime 消费这一准备结果；没有检查会话的原生 Runtime 仍按自身协议编译。

## 最终展示快照

`PreparedPythonPresentation` 保存所选规则完成后的有效 Graph、编译结果、源码资料和只读注册器查询。Architecture、ASCII、Mermaid 与 SVG 共用这一快照。子图按定义及同一编译上下文准备，调用级判断已经在审查阶段完成。

Mermaid 的 `resources` 参数决定本次调用绘制哪些资源：省略、`None` 或空 mapping 只绘制流程，显式传入时绘制所选资源。共享快照提供编译事实，不替调用者选择展示范围。正式 SVG 的主流程及 Nodeset 分片省略该参数，独立资源目录消费当前 workflow 的资源选择；多个分片继续复用同一快照与子图编译结果。源码归属及导入关系保留在 Architecture JSONC，不作为 SVG 目录的展开输入。

展示只查询声明、静态符号位置和已有绑定。延迟实现可以保留 `not_loaded`；其声明定位仍可进入 Architecture。独立展示 API 在传入 Registry 时准备当前事实，因此旧 `compiled` 不能覆盖 Registry 的最新审查结果。正式入口直接传入最终快照。

Architecture 中的 `load_state` 记录生成快照时的观察：`loaded`、`not_loaded` 或 `unknown`。同一架构可能在审查进程尚未绑定实现，而在运行进程已经加载实现。文件与资源源码记录中这些合法状态的变化不触发文档过期；字段缺失、非法状态及源码、归属、规则、样式或来源变化仍参与完整比较。生成头、JSONC 与规范排版继续校验。

`review` 保留 preflight 的健康报告，写入 Architecture 后检查该文件的内容与规范性，然后渲染并原子发布 SVG。它复用已经完成的健康检查。失败时仍保护已有正式 SVG。

## AST 的内部与公开使用

内置分析借用 Target 持有的 AST。`tree/node/implementation_tree` 等公开资料继续返回隔离副本；实现视图只复制选定符号、需要的 imports 和 helper。指标与投影先查缓存，再构造 AST。

会修改语法树的算法复制实际修改的部分：调整 class body 时复制类外壳，归一化指纹时复制目标函数。新增分析器应验证原 AST 前后完全一致，并验证公开视图的深层修改不会影响下一条规则。

## 回归入口

`tests/fixtures/python/review_performance/run_all.py` 在新进程中执行正式 CLI，并在内存中计数，结束后写报告。自动验收检查展示阶段的绑定、规则执行和重复编译，检查真实调用次数及逐文件解析次数。时间使用 monotonic 时钟；代表案例重复三次，报告中位数。

完整门禁包含该沙箱、实际浏览器 SVG 检验、旧规则回归和分发安装验收。沙箱使用 VibeFlow 自身固定的 SDK 资源；详见[运行说明](../../tests/fixtures/python/review_performance/README.md)。

`tests/fixtures/python/review_layout/run_all.py` 验证资源只出现在独立资源面板、各层横竖方向及右侧详情排列，并以正式 CLI 和真实浏览器检查最终 SVG，保留修复前后的观察。
