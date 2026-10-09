# 代码声明与统一插件接入验收

重构起点为 `1b0aa73`，开发版本保持 `0.15.0`。Plugin ABI 为 v3，Rule ABI v1 和原生 Workflow ABI v4 不变。实现遵循 [重构计划](code-plugin-refactor-plan.md)，资源声明、普通语言实现和原生执行协议各自保持明确职责。

## 实现对应关系

| 批次 | 已实现的接口和行为 | 主要验收位置 |
| --- | --- | --- |
| Core 声明基础 | `ContributionBuilder` 收集全部八种资源；`PluginContributions` 冻结资源和参数；合并 Catalog 保留双方来源、拒绝重复 ID | `tests/core/test_contributions.py`、原规则引擎测试 |
| Python SDK | `@node`、`@rule`、`ruleset` 及其他构造接口；固定 `Plugin`；自动源码定位与显式延迟定位；装饰器不注册 | `tests/targets/python/test_code_plugins.py` |
| JS/TS SDK | `@vibeflow/plugin`；保留 worker 中的函数绑定；原生 AOT 导出；包入口按 ESM 和 CommonJS 的实际解析规则定位 | `tests/targets/javascript/test_code_plugins.py` |
| 源码健康 | SDK 声明的别名及遮蔽分析；同文件实现分别审查；共享源码、导入闭包、helper 归属和指标；加载状态如实提供 | 两组规则沙箱、两种 Target 的源码分析测试 |
| 正式入口 | workflow 先加载选中插件，再解析资源引用；validate/quality/review/review-rules、查询和执行共用装配；工厂在原阶段创建与释放 | 正式 CLI、`inspect-resources --config`、生命周期及跨 root 测试 |
| 迁移与发行 | 示例 Node/Rule 与实现放在一起；发行模板使用 `plugins/`；wheel 和发行内核携带同一 SDK；旧扫描、bundle、registry 接入删除 | 独立沙箱、wheel 隔离、两种发行 profile 与真实入口 smoke |

Python 和 JS 领域示例使用参数化 tags 识别模型归属，Node 自己声明浅蓝色。模型、数据变换、分支、Nodeset 和 Loop 的计算继续使用原生路由与执行，规则组合语义没有新增一套 DSL。

插件定义与参数相互独立。未选择、禁用或 planned 插件不加载、不贡献执行资源；同一文件内未列入插件的资源也不可引用。固定声明预览会进行受信模块初始化，框架不调用 Rule、Node 或生命周期工厂。已经初始化的代码仍可被所选规则诊断，延迟且尚未加载的独立实现继续保留检查失败后不导入的保证。

浏览器构建按真实符号依赖保留 Node、helper、Host 和 runtime，排除检查代码及 compiler 的专用 Node 依赖。SDK 测试真实点击浏览器页面并核对数值结果；检查通过或产物可在 Node 中运行不替代这一验收。

真实发行入口发现并修复了 `{run}` 简写的符号依赖遗漏。AOT 现在保留实际函数及其 helper，新增执行回归核对数值结果。运行入口也在健康检查失败后先保存诊断并拒绝执行，避免后续构图编译错误遮挡 Nodeset 的原始健康错误。

## 历史案例和迁移依据

1219 项基线对照、205 项接口场景保留原 ID。[冻结参考](../../../tests/fixtures/rule_parity/reference.json) 和 [上一轮修复机器报告](../../maintainers/evidence/index.md#artifact-d561a82679d8256e) 不改写。原 JSONC 声明、registry 和源码形状移入 `tests/fixtures/resource_migration/`，只由测试夹具显式转换成固定 SDK 插件；产品加载器不读取归档或执行转换。

本轮只迁移启用方式、受信初始化时序、声明来源和旧字段诊断。领域判断、默认健康规则、规则依赖/覆盖/records、扫描范围及原生计算结果继续使用原验收条件。插件引导代码不代替 Rule 判定，也不允许用无关错误遮挡目标反例。

[用户迁移说明](../../../distribution/docs/user/rule-system-migration.md) 给出新旧写法对应，[案例迁移对应表](code-plugin-case-migrations.md) 记录 38 项期待变化及保留的断言。[机器报告](../../maintainers/evidence/index.md#artifact-967a4be5d73ccff3) 保存全部 1424 项当前观察、迁移前期待、诊断位置、执行指标和最终验证结果。

## 最终验收

完整门禁的 12 个阶段全部通过，两个要求的命令退出码均为 0：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

| 验收 | 结果 |
| --- | --- |
| 全量测试 | 1632 通过 |
| Core 贡献与两种 SDK 的直接场景 | 53 通过，包含在全量测试中 |
| Python 集成沙箱 | 138/138 通过 |
| JS/TS 集成沙箱 | 67/67 通过，0 跳过，包含实际浏览器 |
| JS 最小项目 | 真实 AOT 执行通过 |
| 基线规则对照 | 1219/1219 匹配，0 观察错误 |
| 补充接口与领域组合 | 205/205 匹配，0 观察错误 |
| wheel | 隔离安装、SDK 与正式入口通过 |
| 发行 | collaborative/autonomous 构建、真实 Python/JS 入口、解包入口通过 |
| 仓库独立检查器 | 46 项测试通过；全 profile 0 错误、0 警告 |
| 生成物清理 | 门禁末尾 0 清理目标 |

38 项迁移只涉及已批准的接入、加载时序和声明来源变更；其余 1386 项在归一化临时工作目录后沿用原期待。历史观察与冻结参考保持不变。机器报告保留结构化诊断与指标，省略重复的原始 CLI JSON 包装。

`quality/` 继续是独立的标准库工具。受信插件、源码上下文的只读契约、业务类型正确性检查和操作系统沙箱的边界没有改变。
