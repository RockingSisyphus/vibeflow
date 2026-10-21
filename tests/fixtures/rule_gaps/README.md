# 第二轮 Rule、Node 与插件接口补测

独立组默认最多并发 12 个 worker，使用 `--workers N` 或 `VIBEFLOW_TEST_WORKERS=N` 调整，命令行优先。五个接口组使用同一个有上限的任务队列；每个夹具的修改、验证、恢复保持顺序。`--workers 1` 可串行重跑。

测试复制仓库中的正常项目，在临时副本中修改声明或源码，执行真实命令、Target handler、worker 和数值业务。Core finding 案例单独验证语言无关结果契约；其余场景保留实际 Target 资料。用人工指标调用内核，不能替代这里的公开 implementation Rule 组合测试。

## 测试组

| 组 | 覆盖与实际证据 |
| --- | --- |
| `python` | 独立文件的明确空 Ruleset 与启用规则的邻居；同模块自身规则；实际共享/非共享 helper 与调用归属；planned stub 主文件和 helper 的真实导入及 marker |
| `javascript` | typed records 的合法数组、空值、对象和 async；非法 Map/Date/undefined/非有限数字/bigint/循环值；provider 状态和 requires consumer；静态、动态、require 导入；双平台实现的 validate/quality/review/build；普通资源与 Plugin 包冲突由资源准备专项覆盖 |
| `graph` | 不同默认值和新增参数的实现替换及来源；显式 includes；未绑定/冲突输入、参数 schema；源码 consumer 的 typed inputs/有效参数缓存和新 session；直接选择公开 implementation leaf 的真实正常/超限源码；合法和非法 findings 的 Core/Python/JS 边界 |
| `tooling` | 完整 Node shape、已移除分类资源的明确诊断、Rule 端口类型；正式单个 JSON、资源位置和实现尚未执行；混合语言同 ID、项目共享包与双方冲突来源；预览选择一致 |
| `composition` | 领域 Bundle 的模型 Node 在分支、Nodeset、Loop 中实际计算；参数化 tags 归属、非法 helper 模型定义、完整调用路径；Node 自己声明浅蓝色，验证 Architecture、Mermaid 和真实 SVG |

## 运行

从仓库根目录执行；`--work` 必须是尚不存在的目录：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tests/fixtures/rule_gaps/run_all.py \
  --work /tmp/vibeflow-rule-gaps-run \
  --report /tmp/vibeflow-rule-gaps-run.json
```

默认按仓库锁文件准备 TypeScript/esbuild 和 Mermaid/Puppeteer。可通过 `--toolchain /path/to/project-toolchain`、`--renderer /path/to/mermaid-renderer` 复用已按对应锁文件安装的目录；不需要修改测试源码。`--group python` 等参数可重复使用，只运行所选组。

每组使用独立进程和临时项目，保存命令输出、handler 事件、实际产物和 `observations.json`。最终 JSON 列出每项期待、实际资料和具体不匹配原因。退出码为：全部满足 `0`，存在不匹配 `1`，观察进程或环境失败 `2`。空观察组、重复 ID 或残缺记录不能作为通过的覆盖。

正例需要目标 handler 或业务实际执行；负例需要目标诊断与原因，不能由无关异常代替。资料运输测试需要依赖消费者是否执行的证据；非法声明测试需要诊断指向实际资源。正式 CLI 未返回完整 Rule 状态时，同项目另走公开 Target API 取得状态，文件中明确记录证据入口，保留 CLI 的原始结果。

已知问题仍按期望契约报告不匹配，不使用 `xfail`、忽略失败或降低阈值。这组是独立的产品验收入口；报告机制的 pytest 通过，只表示它能正确区分通过、不匹配和观察失败：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/run_tests.py -- \
  tests/integration/test_rule_gaps_reporting.py \
  tests/integration/test_rule_parity_reporting.py
```

各命令的检查范围见[产品检查边界](../../../distribution/docs/user/product-check-boundaries.md)。测试保留生产实现、规则权限和工作流机制；实际结果由上述运行报告记录。

## 目录用途与边界

仅用于：rule_gaps 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。