# 多文件资源案例与迁移对应表

起点为 `3ee7396`。专项场景全部使用真实插件 SDK、正式 CLI 和隔离项目，Core 单测不计入本表。入口为 `sandbox/rule_gaps/run_all.py --group resources`；完整验证默认同时运行这组场景。历史参考、既有 1,219 项规则案例及 205 项接口案例保持原 ID。

## 专项矩阵

| 主题 | 计划最少 | 当前案例 | 稳定 ID 前缀 | 实现与证据 |
| --- | ---: | ---: | --- | --- |
| 登记、启用、隔离 | 40 | 77 | `resources.register.*` | `resource_registration.py`、`resource_registration_extra.py`；inspect-resources/validate JSON、加载 marker、不同 workflow 的配置及声明对照 |
| 源码归属与导入 | 48 | 160 | `resources.ownership.*`、`resources.limits.*` | `resource_ownership.py`、`resource_ownership_extra.py`、`resource_boundaries.py`；真实入口/支撑文件的诊断、位置与退出码 |
| Rule/Ruleset | 32 | 42 | `resources.rules.*` | `resource_rules.py`、`resource_sdk_extra.py`；依赖 records、实际 consumer marker、自定义支撑源码诊断、独立生命周期 SDK |
| 登记后修改 | 32 | 47 | `resources.edits.*` | `resource_edits.py`、`resource_edit_extra.py`；修改前、修改后、恢复后的独立 CLI/build/run，以及样式重新审核 |
| 展示与架构 | 64 | 103 | `resources.display.*` | `resource_display.py`、`resource_display_extra.py`；正式 Architecture、Mermaid、最终 SVG 的浏览器计算样式与几何 |
| 原生运行与打包 | 24 | 46 | `resources.runtime.*` | `resource_runtime.py`、`resource_host_runtime.py`、`resource_runtime_extra.py`；Python/Node.js/浏览器实际执行与生命周期记录 |
| 合计 | **240** | **475** | | |

所有案例保存预期和实际观察，runner 拒绝重复 ID、缺失观察、执行错误及不匹配；不使用 xfail。负例检查目标诊断及严重度、文件/行号和 CLI 退出码，合法邻近输入继续通过。声明缺少精确语法位置时使用声明位置；文件不可用错误保留真实源码引用。

### 重要的连续案例

- 四类资源分别经历新增、删除、改名、移动支撑文件，以及更改实现、规则、颜色、形状。每一步创建新的检查或运行实例，再恢复原版本；不依赖热加载。
- 声明所在模块移到子目录后，支撑文件仍按该模块解析。Python 的包相对导入和 JS/TS 的模块相对导入都通过正式入口验证。
- 同一文件导出两个 BaseLib 时，Host 明确引用第二个库即可合法导入；未声明引用的对照产生 `VF_IMPORT_LAYER`。共享文件仍分别接受每个所属资源的规则，Host 的宽权限不覆盖 Node/BaseLib 的限制。
- Python 也检查同文件两个库的具名导入；Node 与 BaseLib 共处一个文件时，明确的库函数导入通过，直接导入并调用 Node 由导入归属规则拒绝。该反例断言 `VF_IMPORT_LAYER` 的真实位置和退出码；导入阶段已失败，不要求后续静态规则再次产生诊断。原有 Node 耦合规则案例继续保留。
- 每种支持的资源分别检查入口和支撑文件的 449/450/500/501 行；纯资源插件另查声明文件。多文件总量超过 500 行但各文件合法的场景通过，仅支撑文件超限的场景失败。
- Host 的 value、type-only、`.d.ts`、静态 literal dynamic import/require 经过同一归属检查。跨 root 仅允许已登记 workspace root；未登记依赖和已登记但未授权的依赖分别被拒绝。
- provider 可以产生合法 error finding 与有效 records；consumer 仍可消费 records。失败或损坏结果不能伪造资料，consumer marker 不出现。
- Host 的 FIFO、取消、计时器、回执及两个真实实例的状态隔离同时在 Node.js 和浏览器验证。未使用的登记文件不会被强制初始化；Rule/compiler 专用 Node 依赖不进入浏览器运行产物。
- 每类资源遍历全部 14 种公开形状，验证 fill/stroke/text/icon、使用处覆盖和状态样式。失败 review 保留上一版 SVG 和 Architecture 的内容。

## 既有案例的期待迁移

不改写冻结历史观察。以下变更只影响当前实现的期待；其他健康规则、原生运行和规则图期待继续保留。

| 案例 ID | 变化 | 依据与保留断言 |
| --- | --- | --- |
| `core.implementation.library.source_lines.500` | 增加 `BASE_LIB.SOURCE.NEAR_LIMIT` warning | 显式逐文件限制保留 450–500 行警告区间；500 行仍接受，501 行仍报 error |
| `core.implementation.library.source_bytes.60000` | 增加同一近限 warning | 同样保留默认字节限制的警告区间；60000 字节仍接受，超过限制仍拒绝 |
| `js.base.dependency-chain.2` | `source_files` 从 3 增为 4 | 选中插件声明现在作为独立源码记录；依赖深度与接受条件不变 |
| `js.variant.numeric.dependency-4` | `source_files` 从 4 增为 5 | 同上，冻结基线及规则目的不变 |

准确 ID 和旧/新期待由最终机器报告逐项记录；源码指标的输入仍来自 Target，不由测试替代产品规则判定。

测试夹具的旧实现闭包显式展开为固定 SDK `implementation_files` 和 `base_libs`。这个转换仅存在于 `tests/fixtures/support/`，产品不自动发现文件、不恢复旧登记路径。跨 root 夹具补上 Node 自己的库引用与 Python 包初始化文件；缺少库授权的反例仍检查 `VF_IMPORT_LAYER`。

Python 集成项目的 value-shift 生命周期插件明确登记 `value_state.py`，避免只由使用它的 Node 登记共享文件。原有全局配置覆盖警告、真实数值结果和生命周期断言保留。

Architecture 严格集成测试增加 `implementation_graph` 字段及资源/入口断言；公开导入资料增加 `type_only`。JS SDK、worker 和驱动资源的字节快照随实现更新。以上是公开资料扩展，不删除旧执行、契约或规则结果断言。

Python 的展开图去重案例仍要求四次 Nodeset 调用只生成一个细节区；总片区数从主图与细节的 2 个改为 3 个，另一个片区是本轮新增的统一资源区，并检查该区的实际标题。

## 复查入口

```bash
python sandbox/rule_gaps/run_all.py --group resources \
  --work /tmp/vibeflow-resource-cases --report /tmp/vibeflow-resource-cases.json
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full \
  --scratch /tmp/vibeflow-full-verification
python quality/test.py
```

`--work` 使用新目录。保留 `--scratch` 可追踪完整原始 CLI 输出、AOT 产物、图形、浏览器观察和报告。专项 runner 支持复用锁定的 `--toolchain/--renderer`；没有这些参数时自行准备工具链，不以跳过浏览器算通过。

双语言正式示例位于 [资源沙箱](../../sandbox/resources/README.md)。公开接口见 [多文件资源文档](../user/multifile-resources.md)。
