# 源码审查与架构生成性能沙箱

本沙箱通过公开 Python SDK 声明 Node、BaseLib、Rule 和插件，使用正式 CLI 观察分析、绑定、规则执行和展示次数。每个命令在新进程中执行；文件及报告写入指定的外部目录。

```bash
python -B tests/fixtures/python/review_performance/run_all.py \
  --work /tmp/vibeflow-review-performance \
  --report /tmp/vibeflow-review-performance.json \
  --renderer /tmp/vibeflow-renderer
```

`--renderer` 指向按 `tools/mermaid-renderer/package-lock.json` 安装的渲染器目录。完整门禁自动提供它。`--kernel` 可选择冻结的源码目录或发布包的 kernel ZIP；`--installed` 使用当前 Python 环境内安装的 wheel。`--representative` 运行安装验收所需的小矩阵，`--timing-repeats` 默认为 3。

案例覆盖 8/32/80 个 Node 与 1/4/8 个共享 BaseLib、1/4/8 次相同 Nodeset/Loop、100/350/480 行源码、相对导入、跨 root、延迟实现以及 validate/quality/review/导出/checked run。运行案例在业务 Node 中核对数值结果。违规库的 `print` 配相同入口合法对照。

`loaded-architecture-validate` 先登记未绑定时的 Architecture，再在新进程中绑定同一延迟实现并执行正式 validate。它检查合法加载状态变化不会被误报为源码过期。`cache-*` 案例检查参数、调用身份、插件配置、共享实现权限和依赖 records；JSON 输入 `1/2/2` 只执行两次源码 consumer，实际类型不同的 dataclass、字典和 frozenset 分别检查并保留诊断。共享 helper 的权限隔离另由 AST 单测及既有 `helper-ownership` 正式沙箱覆盖。

报告保存稳定案例 ID、CLI 退出码、完整诊断文件、阶段耗时、解析及规则计数和实际产物位置。`review` 产物经过 Architecture、Mermaid、真实浏览器 SVG 的颜色及几何检查，并保存截图。

源码规则的参数、输入 records、插件配置、加载状态、handler、共享 helper 权限及 AST 隔离回归见 `tests/targets/python/test_check_session.py`、`test_rule_sessions.py`、`test_source_ast_reuse.py`；跨 Workflow 的语法复用与权限隔离见 `test_quality_parse_reuse.py`。展示快照回归见 `tests/tooling/test_prepared_presentation.py`。

`--baseline` 只关闭性能和延迟加载的新断言，保留健康审查与 records 正确性期待；冻结旧源码重跑新增案例时可能返回失败。机器报告逐项保存实际结果。

比较两批观察：

```bash
python -B tests/fixtures/python/review_performance/compare.py \
  /tmp/vibeflow-review-before.json /tmp/vibeflow-review-after.json \
  --stage final --output /tmp/vibeflow-review-comparison.json
```

阶段耗时包含嵌套调用，不能相加当作总时间。AST 计数观察 Target 公开视图的完整复制；局部指纹及类外壳复制继续保留。

## 目录用途与边界

仅用于：review_performance 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
