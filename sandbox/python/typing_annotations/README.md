# 类型注解与动态模块访问对照

`before.json` 保存修复前在 `9c443f3` 上的独立正式 CLI 观察：同一 SDK workflow 保留 `Iterable[object]` 时出现三处 `NODE.PURITY.BANNED_CALL`，仅删除注解后通过。案例使用标准库及公开 SDK，没有导入业务项目或 ML 框架。

`probe.py` 生成同流程变体并逐一调用正式 `validate`。14 组涵盖普通签名、Iterable 的别名/限定名称、collections.abc、嵌套/返回/延迟注解、已登记 BaseLib/helper，以及实际动态模块访问、模块字典、遮蔽和注解内的 eval 反例。合法注解通过；反例必须出现目标诊断。`after.json` 为当前观察。

```bash
PYTHONPATH=src:. python -B -m sandbox.python.typing_annotations.probe \
  --work /tmp/vf-typing-probe --report /tmp/vf-typing-report.json
```

每次使用新的工作目录。脚本遇到不匹配返回非零；pytest 的 `test_run_observation.py` 同时检查位置与严重度。该沙箱复现并修复了报告的类型注解根因，MNIST/VibeTrain 的实际训练需在各自项目中验收。
