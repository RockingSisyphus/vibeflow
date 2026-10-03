# f169429 基线规则盘点与迁移对照

本次以 `f169429a8d41` 的实际源码和调用链为依据。目标是确认原有审查能力在 Rule/Ruleset 迁移后仍然成立，既检查违规漏报，也检查正常输入误报。源码中的常量、遗留辅助函数、诊断码和当前自动测试数量都不能单独证明能力已经接入正式检查。

## 原有分工及检查入口

| 层次 | 基线的职责 | 本次验证方式 |
| --- | --- | --- |
| Core | 根据语言无关事实检查源码规模、复杂度、依赖、目录职责、重复逻辑、流程健康及 Nodeset；原生编译真实解析契约、调度、数据边、Loop 和锁 | 对同一事实运行两版公共评估器，并调用真实编译器检查可执行性边界 |
| Python Target | AST 分析、Node 接口和契约、导入时行为、运行纯度、helper 与 BaseLib 归属、实现和依赖指标；把审查结果接入 Node 和工作流报告 | 生成真实 Python 项目，使用正式 `inspect-node` 和公共工作流/BaseLib/源码入口 |
| JS Target | TS 分析、Node/BaseLib/Plugin/Host Extension 的导入、模块状态、完成协议、Promise 和长期事件归属；worker 绑定时也检查插件源码和真实协议 | 真实 audit/build、worker open、质量入口，以及合法编译产物运行 |
| Tooling | 读取声明、工作区、参数及 policy；报告配置字段、资源选择和系统 Node 契约问题，汇聚正式命令结果 | 公共配置检查与两个 Target 的真实项目入口 |

重构后的预期分工仍然是 Core 负责中立规则机制和通用规则，Target 负责语言事实和语言规则实现，Tooling 负责读取和装配。检查进入统一 Rule 通道，并不意味着 Core 应承担 Python/TS 解析。

详细盘点与场景对应分别见 [Core](baseline-rule-inventory-core.md)、[Python](baseline-rule-inventory-python.md)、[JavaScript](baseline-rule-inventory-javascript.md) 和 [Tooling 分支与声明模型](baseline-rule-inventory-tooling.md)。共同的配置主题如下。

## 配置与资源主题

基线 `tooling/project/config_schema.py` 进入配置检查，委托 `schema_node.py`、`schema_common.py`；资源和 Nodeset 判断也在 `config_schema.py`。`schema_resources.py` 提供打包 schema 文本。下表是能力主题，不把重复诊断和每个非法值算成一个独立业务规则。

| 主题 | 判定与主要诊断族 | 对照案例 |
| --- | --- | --- |
| Pipeline 与 Node 身份 | 对象/列表、非空 Node、ID/type、旧字段、调用说明；`CONFIG.SCHEMA.PIPELINE_* / NODES_* / NODE_*` | `tooling.normal`、`pipeline_object` 至 `node_description` |
| 原生图字段 | 边端点、条件、schedule/transfer、entry_mode、max_steps；字段检查与真实编译分开 | `tooling.edges_list` 至 `max_steps_zero`、Core native 图案例 |
| 调用配置与相似性 | config、node_configs、override 标志、similar_to 引用及原因 | `tooling.node_config`、`node_configs`、`config_override`、`similar_*` |
| 展示声明 | 样式对象、允许字段、颜色和系统保留色；新版增加默认分类样式属于新功能 | `tooling.style_*`；已有领域 SVG 沙箱验证实际展示 |
| 原生契约与系统 IO | implemented 调用不能重复声明类型契约；receive 零输入一输出、send 一个 exactly_one 输入零输出 | `tooling.duplicate_contract`、`system_io.*` |
| planned 与 Loop | 状态、flow_kind、显式契约及 stub 字段；Loop body、条件、限额；真实执行能力仍由 Target/原生编译提供 | `tooling.planned.*`、`implemented.config_kind`、Core native Loop 案例 |
| 锁 | key/对象/未知字段/保留前缀；继承、detached 和结果等待由原生编译检查 | `tooling.lock.*`、Core lock 案例 |
| 资源与旧入口 | BaseLib paths/modules、Plugin/Host 选择、global_config、Nodeset 导入，以及已移除的 inline Nodeset、boundary 和 loop 字段 | `tooling.resources.normal`、资源负向及 Core Nodeset 案例 |

`policy` 的 schema、匹配、降级和跳过是旧审查配置机制，审查 hooks 是旧插件机制。按已批准的迁移，应由 Ruleset 参数、覆盖关系和 Rule 实现接替；本次不要求重新引入旧 policy 执行通道。旧版 `flow_kind` 隐式授予权限、external/trusted 自动绕过、effect 不可覆盖同样不属于应恢复的行为。

## 测试取舍与验收依据

对照沙箱位于 [sandbox/rule_parity](../../sandbox/rule_parity/README.md)。同一场景 ID 在独立进程中运行基线和当前版本，报告保留两版实际结果。源码检查采用真实语言代码；通用数值规则使用明确的事实边界，防止把 Target 抽取和 Core 判断的错误混在一起。

每个场景标记 `preserved`、`approved_change`、`baseline_limitation` 或 `new_feature`。例如旧版已经无法统计自定义 `support` 目录依赖链，这是基线局限；旧版能检查该目录的函数数量而新版漏报，则是回退。正常案例先被其他错误拒绝时，是无效夹具，不能当成目标规则有效。

这次增加的是基线能力的对照检测，不修复生产实现。已知回退保持失败预期；完整结果、新增发现和未覆盖边界见 [实际结果](../../sandbox/rule_parity/RESULTS.md)。规则图、资源注册、只读 API、领域判定、SVG 和真实业务执行的现有沙箱仍见 [原覆盖矩阵](../../sandbox/TEST_COVERAGE.md)。

清单覆盖本次查到的实际规则主题及重要分支，并没有穷举所有 schema 非法值、第三方插件判断或运行时输入。配置解析、源码解析、绑定和原生计划失败仍表示没有可执行事实；审查覆盖不能制造这些事实。命令范围保持原设计，不增加孤立源码扫描。
