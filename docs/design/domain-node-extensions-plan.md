# 业务分类与领域规则方案

此方案已被 [Rule/Ruleset、Node 分类与插件系统重构](rule-system-refactor-plan.md) 替代。

模型功能块使用 category/tags，默认浅蓝色由分类声明提供。模型定义归属和一个功能块的判断由领域 Rule 实现；Node 明确选择 Ruleset，插件 bundle 提供分类、Node、Rule 与 Ruleset 资源。核心不预设模型拓扑，继续使用原生 Node/Nodeset/Loop 的组合与执行。

旧方案的 check_sources policy hook、不可覆盖副作用限制和导入类后发现元数据的方式不再作为实施方向。新方案仍保持既有命令范围，不增加项目级领域启用或孤立源码专项扫描。
