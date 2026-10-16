# Python 最小示例

`code_plugin.py` 通过 Python SDK 声明 Node、契约与规则，`nodes.py` 保存实现；workflow 显式选择固定插件对象。`base_lib/` 提供纯算术辅助函数，`nodesets.jsonc` 与 `config_with_imports.jsonc` 演示组合和导入。

```bash
python -m vibeflow build --workspace sandbox/python/minimal/vibeflow_config.jsonc --config sandbox/python/minimal/config.jsonc --out-dir /path/to/candidate-bundle
python /path/to/candidate-bundle/run.py run
```

默认生成 python-package；整个目录可搬迁到提供 Python 与业务依赖的环境。检查不执行契约中的示例输入。运行选项与 API 见 [Python 开发](../../../distribution/docs/user/python-development.md#aot-目录部署)。

## 目录用途与边界

仅用于：python / minimal 案例，验证最小 SDK / CLI 使用、配置加载与短流程执行；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
