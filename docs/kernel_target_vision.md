# Topology Kernel Target Vision

## 核心目标

`topology-kernel` 的目标是成为一个可迁移、可复用、超级严格的拓扑程序内核。它不绑定 Paperflow，也不绑定任何具体业务。开发者只需要编写小型纯函数 node，再用 JSON 配置把 node 和 nodeset 组织成完整程序。

最终目标不是让开发最省事，而是最大限度限制：

- node 间耦合。
- 隐式调用链。
- 代码文件膨胀。
- 副作用污染。
- 文件系统混乱。
- 后期维护不可控。

## 绝对规则

1. node 必须是纯函数。
2. nodeset 也必须表现为纯函数。
3. node 不允许直接读写文件、网络、数据库、浏览器、环境变量。
4. node 不允许调用其他 node。
5. node 不允许 import 其他 node。
6. node 只能依赖框架允许的基础库和项目声明的 `base_lib`。
7. node 必须完整报告自身元数据、输入、输出、语义和参数 schema。
8. 配置文件拥有全部拓扑组织权。
9. 普通图允许环路，但所有环路必须显式声明且有执行次数上限。
10. 未声明 cycle 一律非法。

## 全局出入口

唯一不受 node 规则限制的是框架级全局出入口。

全局出入口不是 node：

- 不进入 node registry。
- 不参与 node purity policy。
- 不能被 node 直接调用。
- 只能由 runtime 在拓扑前、拓扑后或有界循环轮次边界调用。

node 如果需要触发外部能力，只能输出结构化 request/effect/outbox 数据。全局出口读取这些数据执行真实副作用。全局入口把外部结果转换成下一轮拓扑输入。

## 显式有界环路

图允许存在环路，但必须满足：

- 每个 cycle 都在 `pipeline.loops` 中声明。
- loop 必须有 `max_iterations`。
- loop 中每条边必须可追踪执行次数。
- loop 可声明 `until` key 作为提前停止条件。
- runtime 必须能报告每条边的实际执行次数。

目标是允许复杂反馈流程，同时避免无限循环和隐式控制流。

## 嵌套式 nodeset

复杂功能不应该写成巨型 node，而应该用 nodeset 组合多个小 node。

nodeset 的目标规则：

- nodeset 像 node 一样有 `name/type/category/description/version`。
- nodeset 像 node 一样有 `requires/provides`。
- nodeset 内部可以包含 node 和其他 nodeset。
- nodeset 默认隐藏内部中间 key。
- nodeset 只能通过 `exports` 暴露输出。
- nodeset 禁止递归引用。

## Plugin 目标

plugin 应能扩展框架治理规则，而不仅是 runtime hook。

目标插件类型：

- `PolicyPlugin`: 扩展 metadata schema、contract schema、purity rules、文件大小规则。
- `CompilerPlugin`: 扩展 graph compile、edge policy、semantic compatibility、graph optimizer。
- `RuntimePlugin`: 扩展 trace、manifest、progress、cache、GUI 事件。
- `BoundaryPlugin`: 注册或配置全局出入口能力。

示例：

- 要求所有 node 声明最大空间占用。
- 要求所有 node 声明最大输出规模。
- 将 node 文件最大行数从 500 改为 300。
- 限制某类 node 不能使用某个 `base_lib`。

## 必备开发工具

目标 CLI：

```text
topology-kernel validate --config workflow.json
topology-kernel inspect-node --type some.node
topology-kernel inspect-config --config workflow.json
topology-kernel export-mermaid --config workflow.json --output graph.mmd
```

目标检查：

- JSON schema。
- node metadata 完整性。
- contract 完整性。
- import 白名单。
- AST purity。
- node source 行数和字节数。
- node 间 import/call 禁止。
- base_lib purity。
- requires/provides。
- semantic compatibility。
- 显式有界 loop。
- nodeset exports。
- plugin policy。

## Mermaid 目标

框架应能从配置直接生成 Mermaid 图。

导出模式：

- 折叠 nodeset。
- 展开 nodeset。
- 显示 contract key。
- 显示 semantic。
- 显示 loop 和 max executions。
- 显示 policy findings。
- 显示全局出入口。

## 最终使用方式

理想项目结构：

```text
my_project/
  base_lib/
  nodes/
  nodesets/
  configs/
```

开发流程：

1. 写小型纯函数 node。
2. 用 validator 检查 node。
3. 用 nodeset 组织复杂功能。
4. 用 JSON 组织完整拓扑。
5. 用 Mermaid 检查结构。
6. 用 runtime 执行。

该内核的价值在于把复杂程序强行拆成可审计、可组合、低耦合的小块。
