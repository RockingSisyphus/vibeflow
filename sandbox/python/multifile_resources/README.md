# python 多文件资源使用案例

项目通过公开 SDK 声明 Node、BaseLib、Plugin，真实数值结果为 6。Architecture JSONC 是登记的展示配置；运行产物写入仓库外。

```bash
PYTHONPATH=src python -m vibeflow validate --workspace sandbox/python/multifile_resources/vibeflow_config.jsonc --config sandbox/python/multifile_resources/project/configs/workflow.jsonc --json
```

接入说明见 [用户手册](../../../distribution/docs/user/multifile-resources.md)。修改、真实图形与生命周期的系统回归由 tests/tooling/test_resource_preparation.py、test_shared_resource_execution.py 和 test_local_preview.py 执行。

## 目录用途与边界

仅用于：python / multifile_resources 案例，验证Node / BaseLib / Plugin 多文件资源归属与审查；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
