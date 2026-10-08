# Python 运行观测沙箱

公开 SDK 构造真实 workflow，使用默认 `vibeflow.python_io` Ruleset 允许所测试的控制台、进程和线程操作。正式 CLI 分别执行成功、业务异常和启动配置失败。

外部进程持续读取固定 JSON 路径，断言更新时间持续变化、数组信息是独立快照、失败及成功状态正确；同时检查 stdout、stderr、原生文件描述符、子进程、普通线程的控制台输出进入业务日志，终端保留显示，内核报告独立保存。连续案例复用监控位置，检查新运行清空旧信息。

```bash
PYTHONPATH=src:. python -B -m sandbox.python.runtime_observation.probe \
  --work /tmp/vf-runtime-observation --report /tmp/vf-runtime-observation.json
```

使用新的工作目录。不匹配返回非零。pytest 还检查空信息、非法 JSON、参数校验、并发运行隔离、默认 Process Node 更新、项目默认值以及中断退出。

`documentation-release.json` 记录两种正式发行包的文档与提示词一致性，以及从解压包运行 Python/JS 手册 Node 的结果；这些示例在默认 Process Ruleset 下更新 info 并返回原契约输出。
