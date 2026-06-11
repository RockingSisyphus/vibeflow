# Kernel 使用者开发引导

本文面向使用 `topology-kernel` 编写业务 node、nodeset、plugin、base_lib 和 boundary 的开发者。

## Node

- node 只实现 `run_pure(inputs, params) -> outputs`。
- node 不读写文件、网络、数据库、浏览器、环境变量，也不导入 boundary。
- node 输出 key 必须是 `CONTRACT.provides` 中声明的字符串字面量。
- 简单 wrapper node 可以只取输入、调用一个纯 helper/base_lib 函数、返回固定输出；内核会识别这种标准形态，避免把多个 wrapper 误报为 duplicate logic。

## Base Lib

- `base_lib/` 只放纯函数 helper，可被 node 导入。
- `urllib.parse` 默认允许用于 URL 解析等纯逻辑。
- `urllib.request` 仍属于网络 IO，默认禁止；真实下载、HTTP 请求和浏览器操作必须放到 boundary。
- 项目可在 policy 中声明更细的 import 规则：

```jsonc
{
  "policy": {
    "imports": {
      "allowed_modules": ["urllib.parse"],
      "banned_modules": ["urllib.request"]
    }
  }
}
```

模块级规则比 root 规则更精确：`allowed_modules` 可以放开 `urllib.parse`，同时保留 `urllib` root 的整体禁止。

## Nodeset

复杂功能优先拆成多个 node，再用 nodeset 组合。大型项目应把可复用 nodeset 放到独立 JSONC 文件，并在 runnable config 中导入：

```jsonc
{
  "nodeset_imports": [
    {"path": "nodesets.jsonc", "names": ["paperflow.catalog"]}
  ],
  "pipeline": {
    "nodes": [
      {"name": "catalog", "type": "nodeset.paperflow.catalog", "provides": ["outbox.catalog_summary"]}
    ]
  }
}
```

规则：

- `path` 相对当前 config 文件。
- `names` 可省略，表示导入文件中的全部 nodeset。
- 导入的 nodeset 和当前文件内联 nodeset 不允许重名。
- `nodeset_imports` 只导入 nodeset，不导入 pipeline、policy、plugins 或 boundary。

## Boundary

boundary 是唯一允许真实副作用的层。推荐模式是：

1. 纯 node 输出 `effects.*` 或 `outbox.*` 请求。
2. boundary 在 `before_run`、`after_run`、`before_iteration` 或 `after_iteration` 中执行副作用。
3. boundary 返回 `io.*` 结果。
4. 下游纯 node 消费 `io.*` 继续拓扑。

对于需要多轮外部交互的流程，使用显式 `pipeline.loops` 和 boundary iteration，而不是把 boundary 注册成 node。

boundary 中如果出现 `select_*provider`、`rank`、`score`、`audit`、`plan`、`strategy` 等决策形态，内核会给 `BOUNDARY.SMELL.DECISION_LOGIC` warning。该 warning 不阻断运行，但通常表示策略应该前移到 node/base_lib，boundary 只执行请求里已经指定的 provider 或动作。

## Plugin

plugin 可扩展治理规则，但不能绕过绝对规则。若 plugin 放宽可降级规则，必须声明作用域、原因和来源。项目级语义规则，例如更严格的 boundary 决策关键词或 registry 分组策略，适合通过 plugin 增加。

## Registry

推荐按 namespace 分组注册：

```python
def _register_fulltext_nodes(registry):
    registry.register("fulltext.plan_provider_routes", PlanProviderRoutesNode, config_schema={}, config_defaults={})
```

如果 `_register_fulltext_nodes()` 注册了 `literature.*`，内核会给 `REGISTRY.SMELL.NAMESPACE_MISMATCH` warning。迁移期可以保留 warning，但长期应把注册移动到对应分组函数，或用项目 plugin 明确例外。
