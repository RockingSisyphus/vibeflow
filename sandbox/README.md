# VibeFlow 真实使用沙盒

沙盒按 Python 与 JavaScript 两个 Target 组织，直接使用工作区 src。项目通过公开 SDK、配置和正式 CLI 模拟用户接入；运行输出与依赖放入临时工作区，不留在案例目录。

| 场景 | Python | JavaScript |
| --- | --- | --- |
| 最小接入 | [minimal](python/minimal/README.md) | [minimal](javascript/minimal/README.md) |
| 综合数学应用、源码 Rule、warning 与执行矩阵 | [comprehensive_math](python/comprehensive_math/README.md) | [comprehensive_math](javascript/comprehensive_math/README.md) |
| CLI 文件加法 | [cli_addition](python/cli_addition/README.md) | — |
| 对象连续加法 | [object_addition](python/object_addition/README.md) | — |
| 分段数学、互斥分支、汇合与数据旁路 | [piecewise_math](python/piecewise_math/README.md) | — |
| 嵌套 Nodeset、多层循环、执行模式与 trace | [workflow_math](python/workflow_math/README.md) | [workflow_math](javascript/workflow_math/README.md) |
| 多文件插件加法、覆盖与源码修改 | [plugin_addition](python/plugin_addition/README.md) | [plugin_addition](javascript/plugin_addition/README.md) |
| 异步、Capability 与持续端口加法 | — | [async_addition](javascript/async_addition/README.md) |
| 普通图分发与汇合、非法图拒绝、容量与清理后即时补位 | [graph_concurrency](python/graph_concurrency/README.md) | [graph_concurrency](javascript/graph_concurrency/README.md) |
| 完整工作流、CLI、宿主与生命周期 | [integration](python/integration/README.md) | [integration](javascript/integration/README.md) |
| 领域插件与真实数值 | [domain_rules](python/domain_rules/README.md) | javascript/domain_rules |
| 外部规则、资料传递与局部覆盖 | [rule_graph](python/rule_graph/README.md) | [rule_graph](javascript/rule_graph/README.md) |
| Workflow 默认、动态选择、Nodeset 接管与 Node 调用选择 | [rule_selection](python/rule_selection/README.md) | [rule_selection](javascript/rule_selection/README.md) |
| 多文件 Node、库、Plugin 与 Host | [multifile_resources](python/multifile_resources/README.md) | [multifile_resources](javascript/multifile_resources/README.md) |
| 运行日志、状态与异常 | [runtime_observation](python/runtime_observation/README.md) | [runtime_observation](javascript/runtime_observation/README.md) |

错误配置、运行异常和资源释放属于真实使用场景。内部缓存次数、AST/对象身份、历史实现对照及专门的布局回归属于 tests/fixtures，由功能测试或完整仓库验证入口执行，仍保持原覆盖。

## 验证

```bash
python tools/verify_project.py --full
```

单独运行两 Target 的主要沙盒：

```bash
python sandbox/python/integration/run_all.py
python sandbox/javascript/minimal/run_e2e.py
python sandbox/javascript/integration/run_all.py --puppeteer-root /path/to/renderer
python sandbox/python/comprehensive_math/run_all.py
python sandbox/javascript/comprehensive_math/run_all.py
python sandbox/python/rule_selection/run_all.py
python sandbox/javascript/rule_selection/run_all.py
```

默认运行自动清理临时工作区。需要检查产物时使用 runner 的显式工作目录或 --keep-artifacts，目录放在仓库外，检查后及时清理。

覆盖入口见 [TEST_COVERAGE](TEST_COVERAGE.md)，目录职责见 [开发说明](../docs/maintainers/directory-layout.md)，历史原始观察见 [证据索引](../docs/maintainers/evidence/index.md)。

当前两个 integration runner 登记 152 项（Python 103、JavaScript 49）。其中两项是新增的规则选择综合案例；此前 150 项的完整分类与原名见 [任务清单](../docs/maintainers/history/audits/sandbox-task-inventory-workflow-20261010.md)。

JavaScript workflow_math 内含[同一起终点的多条条件边回归](javascript/workflow_math/README.md)：模拟 `done`、`failed` 都进入同一收尾节点，覆盖顺序交换、完全重复与条件重叠。它随 integration 自动执行，无需另行启用。

## 目录用途与边界

仅用于：两个 Target 的真实使用项目和验收 runner；直接加载工作区 src，非沙盒的机制回归归 tests。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
