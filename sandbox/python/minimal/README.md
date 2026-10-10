# Python 最小示例

`manifests/nodes/` 声明 Node 的业务说明、契约、参数和 Ruleset；`nodes.py` 只实现执行方法。项目通过 `vibeflow_project.jsonc` 装配资源，再通过 `config.jsonc` 组合原生 Node 和 Nodeset。

`base_lib/` 提供纯算术辅助函数。源码由所选 `vibeflow.process` Ruleset 检查；`nodesets.jsonc` 与 `config_with_imports.jsonc` 演示原生组合和导入。检查不执行契约中的示例输入。

## 目录用途与边界

仅用于：python / minimal 案例，验证最小 SDK / CLI 使用、配置加载与短流程执行；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
