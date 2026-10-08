# 多文件资源实现与验收

**历史展示结果说明：** 本文记录多文件资源实现时的原始验收。把资源实现、源码文件与导入关系直接展开为正式 SVG 的方案已撤销；当前用户图展示 Workflow 调用与配置所选资源目录。多文件登记、源码审查、运行绑定和 Architecture JSONC 证据继续有效，历史图及计数按当时实际结果保存。

起点为 `3ee7396`，保持 `0.15.0` 开发版本、Plugin ABI v3、Rule ABI v1 和 Workflow ABI v4。实现遵循 [计划](multifile-resources-plan.md)；接口和使用方式见 [公开文档](../user/multifile-resources.md)，案例见 [对应表](multifile-resource-cases.md)。

## 实现对应关系

| 批次 | 实现 | 主要位置 |
| --- | --- | --- |
| 声明与加载 | 四类资源显式支撑文件；BaseLib/Plugin/Host 展示；Host/Plugin 库引用；插件声明和生命周期分别选择规则 | Core Descriptor/source_bundle、两种 SDK、worker、descriptor_loader |
| 源码与规则 | 同一源码归属、真实导入边、逐文件指标；同文件多资源及共享支撑分别检查；Host/Plugin 默认可维护性规则；入口协议仅查真实入口 | 两种 Target 的源码服务、ownership、rule_session、默认 Rule/Ruleset |
| 绑定与运行 | 原生 Python 调用、JS AOT 和浏览器打包；未引用登记文件不强制初始化；单 Host 生命周期及实例状态隔离 | Python registry、JS build、既有 runtime 与 Host ABI |
| 展示与架构 | 一张展开 SVG；统一资源/文件依赖区；源码角色、实际导入、贡献、规则与样式来源进入同一 implementation_graph | resource_architecture、resource_mermaid、Python/JS 正式 review |
| 示例与发行 | 双语言资源示例、475 项正式 CLI 场景、实际浏览器 SVG 检查、公开文档随完整发行包提供 | sandbox/resources、sandbox/rule_gaps、distribution/profiles.jsonc |

规则省略或 `[]` 仍然表示未约束。资源引用不赋予源码所有权，Host 不把自己的 IO 权限传给 BaseLib 或共享文件的其他拥有者。支持路径相对 SDK 声明模块解析；项目文件本身不会产生注册。插件初始化仍是受信加载，诊断不能撤销已经发生的顶层初始化。

独立 Python 生命周期工厂使用 `@lifecycle` 或显式延迟源码引用；JS 的插件包可选择 compiler/runtime 工厂，独立生命周期资源可使用完整 Descriptor。Python Host 运行器、自动发现和热加载均不属于此次实现。

## 正式示例与浏览器证据

- [JS/TS 展开 SVG](../../sandbox/resources/javascript/ARCHITECTURE.svg) 和 [Architecture JSONC](../../sandbox/resources/javascript/ARCHITECTURE.jsonc)：6 个资源、9 个源码文件、29 条关系，包含 Node、BaseLib、插件包、runtime Plugin 和 Host。Host 的 `types.d.ts` 导入保留第 4 行及 `type_only` 资料。
- [Python 展开 SVG](../../sandbox/resources/python/ARCHITECTURE.svg) 和 [Architecture JSONC](../../sandbox/resources/python/ARCHITECTURE.jsonc)：5 个资源、6 个文件、21 条关系。
- [JS/TS 浏览器截图](../../sandbox/resources/evidence/javascript.png)、[Python 浏览器截图](../../sandbox/resources/evidence/python.png) 及相邻的 browser/review JSON、Mermaid 文件记录真实最终产物。目视检查了文字、云形标签、裁切和跨资源连边；模型为浅蓝色，Host 和 BaseLib 保留自身图形和展示。

专项图形场景另遍历全部公开形状，并对最终 SVG 的计算颜色和实际几何做自动断言。正式图通过不替代业务运行；数值计算、原生组合、宿主行为和发行入口分别执行。

## 完整验证记录

执行并通过：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full --scratch /tmp/vf-multifile-final5
python quality/test.py
```

| 验收 | 实际结果 |
| --- | --- |
| 全量 pytest | 1,632 passed |
| Python 原生集成沙箱 | 138/138 |
| JS/TS 原生集成沙箱 | 67/67，包含真实浏览器，0 skipped |
| 冻结历史规则对照 | 1,219/1,219，0 unmatched、0 process_errors |
| 既有接口与领域组合 | 205/205 |
| 新增资源专项 | 475/475：登记 77、归属 160、规则 42、修改 47、展示 103、运行 46 |
| wheel 隔离与 SDK | PASS |
| 完整发行包 | collaborative、autonomous 均 PASS，解包入口真实执行 Python 和 JS 工作流 |
| 仓库独立质量检查 | 0 error、0 warning、0 info |
| 独立质量检查器测试 | 46/46 |
| 完整验证与清理 | 12/12 环节 PASS，cleanup targets: 0 |

[机器报告](../../sandbox/multifile_resources_report.json) 保存全部 1,899 项规则/API/资源观察的稳定 ID、预期、实际诊断、位置、指标与产物位置，以及源码和正式示例的 SHA-256。[完整验证日志](../../sandbox/resources/evidence/full-verification.log) 和 [独立检查器测试日志](../../sandbox/resources/evidence/quality-test.log) 留在仓库中；原始逐项 CLI、构建和浏览器资料仍位于报告记录的 scratch 目录。

既有案例 ID 和冻结历史文件没有改写。四项期待迁移及原因逐项记录在机器报告和案例对应表中；新增同文件 Node/BaseLib 反例以导入阶段的真实 `VF_IMPORT_LAYER` 为目标，不要求导入失败后继续产生静态诊断。

正式示例重新运行了 review，并在真实浏览器中逐资源比较 Architecture 的有效 fill/stroke/text、图标与 SVG；截图经目视检查。验收时包含尚未提交的工作区改动，机器报告保留当时的状态及源码哈希。此次通用 Host 验收不替代 GSKO 自身的生产环境验收。

## 完整分发包

此节保留多文件资源验收时首次构建的记录及归档哈希。后续文档修订可按相同版本重新构建，归档以对应构建记录追踪。

当次通过 `python distribution/build.py` 构建 `0.15.0` 的 collaborative 和 autonomous 两个完整包。构建器自检和两份发布目录的 `verify-kernel` 均通过；ZIP 与上述完整验证生成的对应 ZIP 逐字节一致，共享 kernel 也完全一致。

| 包 | SHA-256 |
| --- | --- |
| `archive/vibeflow-distribution-0.15.0.zip` | `da21380e0b77460911433f56e1494ead494385db4c4cc59f5967621c6407281e` |
| `archive/vibeflow-distribution-autonomous-0.15.0.zip` | `8704d5ee8e9dac7c6f7df0dc9189b04dedc7fd1988efda8ff6f93d92e448c09a` |

发布目录分别为 `dist/vibeflow-distribution/` 和 `dist/vibeflow-distribution-autonomous/`。构建记录见 [分发日志](../../sandbox/resources/evidence/distribution-build.log)；ZIP 和发布目录沿用仓库的忽略规则，源码、文档及验收证据进入 Git。
