# Tooling 剩余分支与声明契约对照

以 `f169429` 的公开 `collect_config_schema_findings` 和 `parse_descriptor_manifest` 为依据。本组不加载业务实现，不以配置解析成功替代真实编译、绑定或执行成功。配置检查属于审查入口；无法构造声明模型的异常另作为解析事实记录。

新增文件是 `tests/fixtures/rule_parity/tooling/schema_variants.py` 和 `descriptor_variants.py`。它们分别增加 203、140 个场景，原来的 67 个基线场景和 2 个新 Rule 选择场景保留。所有新增场景已在独立基线进程实跑校准。

## 配置检查的分支

下列 ID 均以 `tooling.variant.` 开头。`CONFIG.SCHEMA.*` 错误要求原码、严重度及精确诊断集合；Loop 的永久运行和不可达 stop_after 要求原 warning，不能用“命令仍能成功”忽略警告丢失。

| 原判断主题 | 本次补充的场景 ID / 分支 |
| --- | --- |
| Node 配置与旧字段 | `node_configs.key/item/normal`、`override_child_config`、`legacy.registry_key`、`removed.node.category/version` |
| 展示颜色 | `style.{fill,stroke,text}.reserved/hex`：系统保留色与合法十六进制色分别验证 |
| 相似性声明 | `similar.relationship/reason/node/unknown_field/self/normal`，合法引用有真实第二个 Node |
| 异步声明 | `async.invalid/result_missing/result_without_mode/result_not_provided/result_provided`、`async.normal.detached/result_key` |
| 原生契约列表 | `contract.requires.* / provides.*`：非对象、未知字段、重复、逐项缺字段；`cardinality.optional_one/all`；planned 缺契约 |
| planned 行为 | `planned.behavior.*`、非法 kind/对象/字符串；`planned.stub.*` 验证真实允许路径、绝对路径、驱动器、隐藏文件、目录和后缀限制 |
| 边字段 | `edge.removed.{max,max_executions,loop}`、`edge.alias.normal`、`max_steps.one` |
| Loop | `loop.*`：对象、body、旧前缀、未知字段、限额、停止条件；`carry/collect/outputs` 各自列表、对象、mode、逐项缺字段及合法对照；永久/不可达停止 warning |
| 系统 IO | `io.object/unknown/operation/port/on_process/async/receive_two`；原有 receive/send 合法及非法契约场景继续保留 |
| Nodeset | `nodeset.*`：独立声明、旧字段、type、说明、必需契约及列表、pipeline；planned 无 pipeline；Tooling 展开后列表/项目形状 |
| Nodeset imports | `nodeset_imports.list/empty_path/object/missing_path/names/normal` |
| 锁与全局配置 | `node.lock.*`；`global.config/values/allow_config_override/override_child_config`；原有 pipeline 锁分支保留 |
| Plugin/Host/BaseLib 选择 | `resource.{plugin,host,base}.*`：状态、每种元信息类型、planned；Plugin class/type/priority/conflict/config/settings；Host 列表配置及禁用重复合法对照 |
| 旧 policy 数值配置 | `policy.{node_source,complexity,maintainability}.*`：对象、每个字段的非法布尔值、合法 1；complexity 的 null 关闭；source 的 null/0 拒绝 |
| 旧 policy 导入配置 | `policy.{imports,base_lib}.*`：对象、所有字符串列表字段、合法配置 |
| 旧 policy rules 已批准移除 | `policy.removed.*`：旧 downgrade/exemption 的合法和非法输入；基线要求原 schema 诊断，当前统一要求 `CONFIG.POLICY.RULES.REMOVED`，明确记为 approved_change |

这里的 expanded Nodeset 测试只观察公开配置检查器对 Tooling 已展开对象的行为；没有把内部标记作为新用户配置推荐。`schema_resources.py` 提供打包 JSON schema 文本，不是上述资源判断的执行模块；资源选择和 Nodeset 检查实际位于 `config_schema.py`。

## 中立声明模型

以下 ID 以 `tooling.descriptor.` 开头。`DESCRIPTOR.MODEL` 是沙箱对公开 `DescriptorModelError` 的观察标签，**不是新增生产诊断码**。测试同时要求异常原因，避免任意一次加载失败冒充正确拒绝。所有六类资源有正常声明和未知字段反例。

| 声明主题 | 实际分支 |
| --- | --- |
| 根与 kind | 根对象、缺 kind、未知 kind、目录 kind 不匹配 |
| Node 身份 | 每个必需字段、flow_kind、external 布尔、author/category 类型、tags/base_libs 列表/空项/重复/元素类型 |
| 契约 | requires/provides 对象列表、每个必需字段、cardinality、重复、未知字段；语义必须精确覆盖、语义列表；params 对象与 examples 对象列表 |
| 实现 | 必需字段、语言与 js/ts 归一化、合法/空/重复/未知 Target、语言与 Target 匹配、completion、Python suspend、重复 Target 实现 |
| Source locator | 缺 kind/ref、未知 kind、空 ref、export 类型、未知字段 |
| Node capabilities | 对象列表、id、operations 列表、未知字段 |
| BaseLib/Host/Plugin | 空实现、重复/非法依赖和 external_packages、自依赖；Host Python 实现；Target 列表；Plugin Target 覆盖与 priority/config/factory 默认 export |
| 数据 schema | id 别名与冲突、representation、schema 对象、draft 2020-12、非有限 JSON 数值 |
| Capability | operations 对象/非空/项目、未知字段、输入输出、completion、Target |

`contract.examples.outputs_baseline_valid` 记录一个解析 API 差异：基线 parser 接受 outputs，新版模型提前拒绝。Python 正式 Node 审查在基线已另行拒绝 examples.outputs，不能据此声称 Python 丢失了审查能力。JS 正式入口对照另记录于 JS 清单及统一结果。本测试保留 parser 旧接受预期，让这处变化可见；若需确认它是否属于有意的公开契约变更，应依据具体迁移决定，不根据当前结果自动改为通过。

本清单覆盖盘点到的判断分支与重要合法对照，没有穷举任意非法 JSON、字符串值或插件自定义 schema。实际原生能力和 Target 所有权检查由其他组单独验证。
