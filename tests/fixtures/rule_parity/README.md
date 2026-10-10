# 基线规则对照沙箱

独立 Target/版本观察默认最多并发 8 个 worker。使用 `--workers N` 或 `VIBEFLOW_TEST_WORKERS=N` 调整，命令行优先；`--workers 1` 可串行重跑。Target 内共享资料的场景仍按原顺序执行。

这组测试保留 `f169429` 和修复前 `15adf51` 的冻结观察，检查当前工作区是否漏掉旧规则或错误拒绝合法输入。它与领域插件、规则图及图形沙箱互补，已接入 `verify_project.py --full`。

规则清单见 [基线盘点](../../../docs/design/history/baseline-rule-inventory.md)。这里按能力组织场景，不把一个诊断码等同于一条独立 Rule。测试夹具在临时目录生成；Python 的基线使用旧类声明，当前版本使用选中插件的代码声明及显式源码登记。历史输入的适配只发生在测试中。

```bash
python tests/fixtures/rule_parity/run_all.py \
  --current-only \
  --work /tmp/vibeflow-rule-parity-run \
  --report /tmp/vibeflow-rule-parity-run.json
```

`--work` 应是新目录，保留当前夹具、日志和原始观察；省略时自动清理临时目录，报告仍保存。`--target core|tooling|python|javascript` 可重复指定。`--current-only` 从 `reference.json` 关联两版历史观察，只运行当前实现，并验证历史 ID 没有丢失。JS 可用 `--toolchain` 复用锁定工具链。

显式重跑两版历史审计时，省略 `--current-only` 并使用 `--baseline f169429`。该入口读取本地 Git，并按两版锁文件准备工具链。历史文件不被日常验证改写；迁移理由见 [声明迁移](../../../distribution/docs/user/rule-system-migration.md)。

退出码：`0` 表示所运行案例符合预期；`1` 表示发现行为差异或基线夹具不符合预期；`2` 表示观察进程或所需工具未正常运行。报告将基线夹具问题与确认的产品回退分开，不能用任意一个失败代替目标规则的拒绝。

| 分组 | 实际入口与证据 |
| --- | --- |
| `core` | 公共通用事实评估、真实原生图编译、工作流/Nodeset 检查，以及默认规则选择和子图编排 |
| `tooling` | 公共配置检查和声明模型解析：声明形状、契约、图字段、资源选择、系统 IO 与 planned 规则；解析异常另外标注 |
| `python` | 正式 `inspect-node`、工作流检查、公开 BaseLib 和源码分析；保留诊断、位置、指标及导入标记 |
| `javascript` | 正式 audit/build、真实 Plugin worker、TS 质量分析和成功产物的数值运行 |

预期分为四种：保持原有能力、用户已批准的语义变化、基线自身局限、新功能。已批准的变化有明确说明，例如副作用授权来自规则选择。已确认的漏报仍要求原有错误或警告出现，不使用 `xfail`，也不根据当前结果自动改写预期。

比较器检查诊断码和严重度、接受/拒绝、指标，以及指定的诊断位置和原因；部分精确集合案例还拒绝新增诊断。JSON 同时保存两版原始观察，方便判断某个结果来自真实目标检查，还是前面的配置、绑定或工具错误。

少量场景明确记录旧 CLI 本身的报告序列化崩溃：必须声明 `ERROR`、拒绝、进程运输类型、非零退出码和具体异常原因。它们属于基线局限，对应审查判断另用公开 validator 验证。普通未知异常仍是夹具/执行问题，不能满足所需 Rule 诊断。

比较器自身的测试通过隔离入口运行：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/run_tests.py -- \
  tests/integration/test_rule_parity_reporting.py
```

报告机制的 pytest 通过不能替代真实沙箱。完整门禁实际运行 current-only 全组，不匹配或观察错误使门禁失败。空组、重复 ID、残缺记录和丢失历史 ID 均不能算通过。修复前事实见 [历史检查](RESULTS.md)，最新验收见完整修复结果。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。

## 目录用途与边界

仅用于：跨 Target 规则一致性的案例定义、固定期望及 reference.json 输入基线；运行报告不能覆盖基线。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
