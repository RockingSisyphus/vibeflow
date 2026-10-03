# 代码插件重构的案例迁移对应表

起点 `1b0aa73`。1219 项基线对照和 205 项补充场景保留原 ID；[历史观察](../../sandbox/rule_repair_report.json) 与 [冻结参考](../../sandbox/rule_parity/reference.json) 保持原文件。

下表记录 38 项因本轮已批准的声明、启用入口或加载时序改变而迁移的期待。其余 1386 项在归一化临时工作目录后沿用原期待。3 项 JS 导入资料案例仅工作目录前缀变化，不属于行为迁移。[验收机器报告](../../sandbox/code_plugin_report.json) 保存完整当前观察与原期待对应。

| 案例 ID | 原诊断 | 当前诊断 | 理由与保留断言 |
| --- | --- | --- | --- |
| `tooling.plugin_object` | `CONFIG.SCHEMA.PLUGIN_OBJECT` | `PLUGIN.SELECTION.MIGRATION` | 旧对象式插件表移除，明确报告迁移；仍要求显式插件列表。 |
| `tooling.variant.plugin.class` | `CONFIG.SCHEMA.PLUGIN_CLASS` | `PLUGIN.SELECTION.SOURCE` | 原 class 导出定位反例迁为非法 source.export；仍在业务执行前拒绝。 |
| `tooling.variant.plugin.conflict` | `CONFIG.SCHEMA.PLUGIN_CONFLICT` | `PLUGIN.SELECTION.MIGRATION` | workflow 不再选择覆盖策略；固定资源的重复 ID 明确冲突，旧 conflict 字段报告迁移。 |
| `tooling.variant.plugin.empty` | `CONFIG.SCHEMA.PLUGIN_MODULE` | `PLUGIN.SELECTION.SOURCE` | 空插件选择缺失显式 source，仍在装配前拒绝。 |
| `tooling.variant.plugin.priority` | `CONFIG.SCHEMA.PLUGIN_PRIORITY` | `PLUGIN.SELECTION.PRIORITY` | 优先级属于插件定义；保留 planned 记录中的整数优先级验证。 |
| `tooling.variant.plugin.settings` | `CONFIG.SCHEMA.PLUGIN_CONFIG` | `PLUGIN.SELECTION.MIGRATION` | 移除旧 settings 字段，配置使用 config；旧写法报告迁移。 |
| `tooling.variant.plugin.type` | `CONFIG.SCHEMA.PLUGIN_TYPE` | `PLUGIN.SELECTION.SOURCE` | 原生命周期类型选择反例迁为非法 source.kind；生命周期职责由固定插件导出。 |
| `tooling.variant.resource.plugin.metadata_category` | `CONFIG.SCHEMA.RESOURCE_METADATA_STRING` | `PLUGIN.SELECTION.MIGRATION` | workflow 不再重复声明资源 metadata，旧 category 字段报告迁移。 |
| `gaps.graph.javascript.invalid.input_conflict` | `RULE.INPUT.CONFLICT` | `RULE.INPUT.CONFLICT` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.javascript.invalid.input_unbound` | `RULE.INPUT.UNBOUND` | `RULE.INPUT.UNBOUND` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.javascript.invalid.params_type` | `RULE.PARAMS.SCHEMA` | `RULE.PARAMS.SCHEMA` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.javascript.invalid.params_unknown` | `RULE.PARAMS.SCHEMA` | `RULE.PARAMS.SCHEMA` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.python.invalid.input_conflict` | `RULE.INPUT.CONFLICT` | `RULE.INPUT.CONFLICT` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.python.invalid.input_unbound` | `RULE.INPUT.UNBOUND` | `RULE.INPUT.UNBOUND` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.python.invalid.params_type` | `RULE.PARAMS.SCHEMA` | `RULE.PARAMS.SCHEMA` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `gaps.graph.python.invalid.params_unknown` | `RULE.PARAMS.SCHEMA` | `RULE.PARAMS.SCHEMA` | 规则图诊断位置：JSONC 声明 → SDK 声明文件；错误码、位置要求和零 handler 调用不变。 |
| `js.gaps.bundle.base_lib.conflict` | `DESCRIPTOR.CONFLICT` | `DESCRIPTOR.CONFLICT` | 重复资源由 SDK 收集合并发现；保留 previous/current 双方来源，构建和业务仍不发布。 |
| `js.gaps.bundle.base_lib.dangling` | `DESCRIPTOR.PATH.MISSING` | `PLUGIN.DECLARATION.LOAD` | 缺失的直接导入资源在受信插件装载阶段失败；后续业务、构建仍不执行。 |
| `js.gaps.bundle.capabilities.conflict` | `DESCRIPTOR.CONFLICT` | `DESCRIPTOR.CONFLICT` | 重复资源由 SDK 收集合并发现；保留 previous/current 双方来源，构建和业务仍不发布。 |
| `js.gaps.bundle.capabilities.dangling` | `DESCRIPTOR.PATH.MISSING` | `PLUGIN.DECLARATION.LOAD` | 缺失的直接导入资源在受信插件装载阶段失败；后续业务、构建仍不执行。 |
| `js.gaps.bundle.data_schemas.conflict` | `DESCRIPTOR.CONFLICT` | `DESCRIPTOR.CONFLICT` | 重复资源由 SDK 收集合并发现；保留 previous/current 双方来源，构建和业务仍不发布。 |
| `js.gaps.bundle.data_schemas.dangling` | `DESCRIPTOR.PATH.MISSING` | `PLUGIN.DECLARATION.LOAD` | 缺失的直接导入资源在受信插件装载阶段失败；后续业务、构建仍不执行。 |
| `js.gaps.bundle.host_extensions.conflict` | `DESCRIPTOR.CONFLICT` | `DESCRIPTOR.CONFLICT` | 重复资源由 SDK 收集合并发现；保留 previous/current 双方来源，构建和业务仍不发布。 |
| `js.gaps.bundle.host_extensions.dangling` | `DESCRIPTOR.PATH.MISSING` | `PLUGIN.DECLARATION.LOAD` | 缺失的直接导入资源在受信插件装载阶段失败；后续业务、构建仍不执行。 |
| `js.gaps.bundle.plugins.conflict` | `DESCRIPTOR.CONFLICT` | `DESCRIPTOR.CONFLICT` | 重复资源由 SDK 收集合并发现；保留 previous/current 双方来源，构建和业务仍不发布。 |
| `js.gaps.bundle.plugins.dangling` | `DESCRIPTOR.PATH.MISSING` | `PLUGIN.DECLARATION.LOAD` | 缺失的直接导入资源在受信插件装载阶段失败；后续业务、构建仍不执行。 |
| `tooling.gaps.javascript.category_list.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.javascript.category_list.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.javascript.category_object.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.javascript.category_object.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.javascript.category_valid.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.javascript.category_valid.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_list.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_list.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_object.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_object.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_valid.review-rules` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |
| `tooling.gaps.python.category_valid.validate` | `DESCRIPTOR.INVALID` | `DESCRIPTOR.INVALID` | 删除 category 后，在 Node 的 SDK 声明上检查旧字段；正式 CLI 和预览都拒绝，handler 不执行。 |

## 测试输入迁移

旧资源 JSONC、bundle 和 registry 输入归档在 `tests/fixtures/resource_migration/`。测试在临时目录显式把原输入转换成固定 SDK 插件，随后使用正式产品入口检查；Core 的纯内存规则图案例继续直接验证 Core。生产加载器不扫描这些归档、不执行转换，也不恢复旧注册路径。

公开 Python/JS 领域示例、规则图示例和发行模板把声明与实现放在一起。导入前阻断案例使用明确的延迟 SourceLocator，以继续验证未加载实现的阻断保证。受信插件顶层初始化案例通过真实 marker 确认已经执行，并核对规则仍能报告错误。

Python 集成沙箱另外迁移了原有生命周期选择、planned stub 的项目相对路径，以及一个显式非法 display_name 类型反例。SDK 为省略的 display_name 提供默认值，所以类型反例必须提供真正的非法类型；没有降低类型校验。记录文件写入和全局状态配置示例各自显式选择允许对应效果的 Ruleset，原有数值、hook、Mermaid/SVG 断言保留。

## 新接口的直接验收

新增测试直接编写语言 SDK，不经过历史夹具转换：

- `tests/core/test_contributions.py`：全部资源类型、冻结、重复 ID、双方来源及非法对象。
- `tests/targets/python/test_code_plugins.py`：固定导出、选中范围、别名与源码归属、延迟阻断、实际原生运行、参数隔离和工厂释放。
- `tests/targets/javascript/test_code_plugins.py`：同文件多个资源、具名绑定、Rule worker、AOT、实际浏览器运行、Host/Capability 和 ESM 包入口。

正式验证继续运行两组规则沙箱、两种 Target 的原生串行/分支/Nodeset/Loop、wheel 隔离和两个发行 profile；不使用 xfail，不用无关装配错误替代目标健康规则反例。
