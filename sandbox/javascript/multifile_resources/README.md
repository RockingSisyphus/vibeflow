# javascript 多文件资源使用案例

项目通过公开 SDK 声明 Node、BaseLib、Plugin 和 Host，真实数值结果为 6。Architecture JSONC 是登记的展示配置；运行产物写入仓库外。

```bash
PYTHONPATH=src python -m vibeflow validate --workspace sandbox/javascript/multifile_resources/vibeflow_config.jsonc --config sandbox/javascript/multifile_resources/workflow.jsonc --json
```

接入说明见 [用户手册](../../../distribution/docs/user/multifile-resources.md)。修改、真实图形与生命周期的系统回归由 tests/fixtures/rule_gaps/run_all.py --group resources 执行。
