# 内核开发与验证

本文说明内核维护的修改边界、验证入口和文档装配；业务项目接口见[使用者文档](../README.md#使用者开发)。

## 修改边界

- Core 保持语言无关；
- Block Compiler 不加载项目文件或语言实现；
- Python 与 JavaScript Target 彼此隔离；
- Tooling 承担文件系统与 CLI 编排；
- 公共行为同时更新 Python、JavaScript presenter、文档和测试。

仓库可能包含未提交修改。实施变更时在现有工作树上合并，避免重置或覆盖无关内容。

## 验证层级

开发测试依赖通过 `python -m pip install -e '.[test]'` 安装，包括 pytest 与 pytest-xdist。

快速回归运行相关 pytest 文件。完整验收使用：

```bash
python tools/verify_project.py --full
```

独立运行 pytest 使用隔离入口：

```bash
python tools/run_tests.py -- tests/core/test_result_scope.py
python tools/run_tests.py
```

测试调度默认最多使用 12 个 worker。以下入口都接受 `--workers`：

```bash
python tools/verify_project.py --full --workers 4
python tools/run_tests.py --workers 2 -- tests/core
python tests/fixtures/rule_parity/run_all.py --current-only --workers 12
python tests/fixtures/rule_gaps/run_all.py --workers 12
VIBEFLOW_TEST_WORKERS=4 python tools/verify_project.py --full
```

优先级为命令行、`VIBEFLOW_TEST_WORKERS`、默认值 12；`--workers 1` 使用串行调度，0、负数和非整数报参数错误。该设置只控制验收调度；业务并发由各分发调用的 `config.max_concurrency` 独立控制，不存在全局业务线程池设置。

pytest 使用独立进程，并按文件分组；同一文件内的测试按顺序执行。每个 worker 有自己的工作目录和临时资料。沙箱使用线程池调度隔离子进程；接口组及资源工作进入同一个队列；display/edits 再按独立资源类别与额外案例拆分，避免嵌套线程池叠加并发数。组内的修改、验证、恢复步骤保持顺序；完整验收各阶段及共享一套产物的旧集成场景也保留原先顺序。

该入口固定本仓 `src`、关闭用户站点和自动加载的第三方 pytest 插件，并明确加载 xdist 与工作目录适配器，在结束后移除临时目录。这样运行时默认的 `runs/vibeflow` 与测试缓存不会污染工作树。

完整入口覆盖仓库质量、pytest、Python sandbox、JavaScript integration、真实浏览器、基线规则对照、接口与多文件资源沙箱、wheel 隔离、双发行 smoke、确定性归档及清洁工作树检查。

并发改动的专项入口为两个 Target 的 `sandbox/<target>/graph_concurrency/run_all.py`。它们固定验证正常容量 12、容量 4 和默认 8 的真实峰值及清理后补位，并要求回收兼分发、断路配置同时被 `validate` 和 `build` 拒绝。JavaScript 必须提供 `--puppeteer-root` 才能计为完整通过；缺少浏览器时报告 `REDUCED`。命令、逐项判定和报告位置见 [Python 沙箱](../../sandbox/python/graph_concurrency/README.md)与 [JavaScript 沙箱](../../sandbox/javascript/graph_concurrency/README.md)。发布验证保留本次实际批次，不把此前测试结果改称新全量。

资源专项通过正式 CLI 覆盖声明归属、规则、修改、展示和原生运行。固定输入与验证命令见 [Python 多文件资源](../../sandbox/python/multifile_resources/README.md)和 [JavaScript 多文件资源](../../sandbox/javascript/multifile_resources/README.md)；图形判定与单独重跑命令见 [Python 资源目录](../../tests/fixtures/python/resource_sections/README.md)、[JavaScript 资源目录](../../tests/fixtures/javascript/resource_sections/README.md)及 [SVG 布局](../../tests/fixtures/python/review_layout/README.md)。

仓库自检器为：

```bash
python repo_check/run.py --profile all
```

它检查目录、依赖方向、Target 隔离、生成物、文档链接和发行源。用户项目使用 `python -m vibeflow quality-check` 或发行包装器的 `quality`。

## 文档维护

- `distribution/docs/user/` 面向业务项目的开发者与 AI，说明如何声明、启用、检查、构建和查看资源；
- `distribution/prompts/` 为 AI 提供任务导航和 profile 协议，链接使用手册中的完整规范；
- `docs/design/` 的系统架构与执行模型解释当前内核，仅保留仍待执行的计划，已完成任务的有效知识并入当前规范；
- `docs/maintainers/` 面向内核开发者，记录修改、验证和发行操作；
- 同一规范在一个位置完整定义，其他文档链接到对应主题；
- 示例按公开 SDK 与实际 schema 编写，加载边界在相关操作处说明；
- 优先描述操作及结果，必要限制准确定位到适用场景。退役计划和报告删除，历史溯源使用 Git。

修改文档后运行文档一致性与可执行示例测试，再按[发行装配](release.md)构建两个包。检查生成 AGENTS 的阅读入口、复制后的链接和公开示例，分别核对内容正确性与包内字节一致性。

## 清债回归职责

项目清单、可见声明唯一性、默认/显式跨 root 导入及搬移 AOT 由 `tests/tooling/test_project_inventory.py`、`test_project_dependency_scope.py` 和 `test_project_preparation.py` 覆盖。正式质量命令的默认、替换、空选择及旧参数拒绝由 `test_root_quality_command.py` 覆盖；源码测量和图算法用当前事实收集器与规则求值器验证，不保留独立旧扫描接口。效果分析的别名、策略和定位由 `tests/targets/python/test_source_effect_parameters.py` 与规则沙箱覆盖。

JavaScript 源码拼接顺序断言已退役，生成物语义由两端 AOT 和 JavaScript integration 的真实运行验证；SVG 标签测试仅保留对齐、边界和文本等算法契约，最终资源视图、离线和历史交互由真实浏览器测试验证。不要用测试数量下降代替覆盖和耗时比较。
