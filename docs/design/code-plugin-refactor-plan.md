# 代码声明与统一插件接入

起点：`1b0aa73`。开发版本保持 `0.15.0`；Plugin ABI 升至 v3，Rule ABI v1 和 Workflow ABI v4 不变。

## 已确定的目标

Core 收集和校验语言无关的 Descriptor，冻结为 PluginContributions。Python SDK 和 JS/TS SDK 保存语言实现及源码位置；workflow 的显式 plugins 列表决定本次 Catalog。普通模块导入没有注册作用。全部自定义资源通过插件贡献，内置规则使用同一收集接口。

插件导出固定对象，配置仅影响规则上下文及生命周期实例，不能生成不同资源、契约或规则图。入口及直接导入是受信初始化；已经执行的顶层副作用仍可被规则报告，但不能提前阻断或撤销。独立延迟实现继续支持导入前检查。

保留原生 Node、Nodeset、Loop 的组合与执行，现有规则图语义和命令范围。Node 明确选择 Ruleset，省略或空列表表示未约束。继续不使用 category，也不引入孤立源码扫描、自动发现、热加载、自动修复或操作系统沙箱。

## 实施及验收

| 批次 | 实现 | 验收 |
|---|---|---|
| 1 | ContributionBuilder、冻结、来源与内置资源合并 | 纯内存资源校验、双方冲突来源、不可变配置 |
| 2 | Python 装饰器、固定 Plugin、延迟实现、按 workflow 装配 | 同文件资源、未选资源、配置隔离、实际运行 |
| 3 | @vibeflow/plugin、worker 声明运输与具名绑定 | JS/TS Rule、AOT、浏览器实际运行 |
| 4 | SDK 声明及源码归属分析 | 别名和遮蔽、helper、复杂度、导入状态 |
| 5 | 正式命令共用装配与生命周期 | validate/quality/review/review-rules、查询、构建及运行范围一致 |
| 6 | 项目、发行模板、案例和文档迁移，删除旧入口 | 全量测试、两组真实沙箱、wheel、两个发行 profile 与 smoke |

旧 descriptors、bundle、项目 registry 不再加载，正式报告给出迁移诊断。Nodeset 导入不隐式启用插件。声明预览加载受信入口，框架不调用 Rule、Node 或生命周期工厂。

1219 个基线对照和 205 个接口场景保留 ID 与冻结历史。只迁移明确改变的接入方式和初始化时序，其余审查行为及执行结果继续作为回归约束；不使用 xfail。

完成验收：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

`quality/` 始终使用标准库独立检查仓库，不依赖被检查的内核。
