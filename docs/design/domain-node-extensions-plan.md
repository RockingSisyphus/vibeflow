# 业务分类与领域规则方案

本页是早期业务分类方案。其规则组合由[Rule/Ruleset 重构](rule-system-refactor-plan.md)承接，资源接入随后改为[代码插件](code-plugin-refactor-plan.md)。当前 Node 声明见[规则与 Node](../user/rules-and-nodes.md)。

模型功能块使用 tags/metadata，浅蓝色由完整 Node 声明提供。模型定义归属与功能块判断由领域 Rule 实现；Node 选择 Ruleset，固定代码插件贡献资源。原生 Node/Nodeset/Loop 的组合与执行承载模型拓扑。

旧方案的 check_sources policy hook、不可覆盖副作用限制和导入类后发现元数据的方式不再作为实施方向。新方案仍保持既有命令范围，不增加项目级领域启用或孤立源码专项扫描。
