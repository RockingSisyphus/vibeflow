# 类型注解与动态模块访问对照

`before.json` 保存修复前在 `9c443f3` 上的独立正式 CLI 观察：同一 SDK workflow 保留 `Iterable[object]` 时出现三处 `NODE.PURITY.BANNED_CALL`，仅删除注解后通过。案例使用标准库及公开 SDK，没有导入业务项目或 ML 框架。

`probe.py` 生成同流程变体并逐一调用正式 `validate`。14 组涵盖普通签名、Iterable 的别名/限定名称、collections.abc、嵌套/返回/延迟注解、已登记 BaseLib/helper，以及实际动态模块访问、模块字典、遮蔽和注解内的 eval 反例。合法注解通过；反例必须出现目标诊断。`after.json` 为当前观察。

```bash
PYTHONPATH=src:. python -B -m tests.fixtures.python.typing_annotations.probe \
  --work /tmp/vf-typing-probe --report /tmp/vf-typing-report.json
```

每次使用新的工作目录。脚本遇到不匹配返回非零；pytest 的 `test_run_observation.py` 同时检查位置与严重度。该沙箱复现并修复了报告的类型注解根因，MNIST/VibeTrain 的实际训练需在各自项目中验收。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。

## 目录用途与边界

仅用于：typing_annotations 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
