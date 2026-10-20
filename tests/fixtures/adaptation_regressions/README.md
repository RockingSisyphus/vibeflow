# 资源与审查适配回归

这组沙箱通过公开 SDK 创建独立项目，再调用正式 CLI、规则接口和真实 JS worker。它覆盖维护审查中的 A01–A10，以及贡献装配、JS 分析复用和旧沙箱入口迁移 S01–S03。

```bash
python -B tests/fixtures/adaptation_regressions/run_all.py \
  --toolchain /path/to/javascript-toolchain \
  --renderer /path/to/puppeteer \
  --work /tmp/vibeflow-adaptation-new \
  --report /tmp/vibeflow-adaptation-report.json
```

`--work` 必须使用新目录。普通运行默认 12 个 worker，可通过 `--workers` 修改。`--group core_sdk/python_runtime/javascript/structure` 可以定向运行；传入多个 `--group` 可组合。JS 工具链和渲染器复用完整验证的安装目录。

报告保留稳定案例 ID、期待、实际结果、完整诊断、退出码、计数、marker 和产物位置。所有负例都有相同入口的合法对照。观察异常、不匹配或必要案例缺失都会让验证失败。Core DAG 探针只输出对象数量和共享关系，避免观察本身展开大量对象。

| 组 | 主题 | 主要证据 |
| --- | --- | --- |
| `core_sdk` | A01、A08、S01 | 实际源码身份、延迟绑定、合法别名、Record 共享和隔离、缓存内容及类型区分、固定贡献与配置隔离 |
| `python_runtime` | A02、A04、A06、A07 | compiler 阶段与产物、纯源码查询、inspect 的准备次数、实际调用关联与 policy 优先级 |
| `javascript` | A03、A09、A10、S02、S03、A05 | 有限图运输、清理与根因、Host 依赖闭包、实际分析次数、正式 Ruleset 路径、四类资源源码关系 |
| `structure` | A05 | Python 支撑文件、独立库与插件贡献关系；未登记依赖拒绝 |

性能对照使用冻结源码和当前源码，各运行三次，按单 worker 顺序启动新进程：

```bash
python -B tests/fixtures/adaptation_regressions/timings.py \
  --baseline /path/to/frozen/src \
  --toolchain /path/to/javascript-toolchain \
  --work /tmp/vibeflow-adaptation-timings-new \
  --report /tmp/vibeflow-adaptation-timings.json
```

时间用于定位和比较；自动回归通过确定性计数判断是否仍有重复工作，不设置跨机器的墙钟门槛。`verify_project.py --full` 已包含这组沙箱。历史证据与修复结果记录在 [维护说明](../../../docs/maintainers/history/adaptation-repair-20261005.md)。

完整分发包的隔离代表性验收使用：

```bash
python -B tests/fixtures/adaptation_regressions/release_probe.py \
  --package /path/to/vibeflow-distribution \
  --toolchain /path/to/javascript-toolchain \
  --work /tmp/vibeflow-release-probe-new \
  --report /tmp/vibeflow-release-probe.json
```

`--package` 也接受完整分发 ZIP。脚本复制完整包并从 `kernel/vibeflow-kernel.zip` 解压内核；各观察进程的 `PYTHONPATH` 只包含该内核。夹具和计数观察器复制到新目录，报告保存内核 SHA、实际模块位置、案例、计数、原始产物及包内使用手册和 AI 提示词的核对结果。

该代表组覆盖 SDK 来源一致性、Rule records、compiler 产物、多文件 Host 实例和分析复用。检查旧包以验证脚本流程时传入 `--purpose script-validation`；这类报告始终标记 `acceptance: false`，不作为新版发行验收。新分发包的报告仅在全部期待通过且没有观察错误时标记验收通过。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。

## 目录用途与边界

仅用于：adaptation_regressions 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
