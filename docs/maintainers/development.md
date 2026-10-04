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

快速回归运行相关 pytest 文件。完整验收使用：

```bash
python tools/verify_project.py --full
```

独立运行 pytest 使用隔离入口：

```bash
python tools/run_tests.py -- tests/core/test_result_scope.py
python tools/run_tests.py
```

该入口在临时工作目录执行测试，固定本仓 `src`、关闭用户站点和自动加载的第三方 pytest 插件，并在结束后移除临时目录。这样运行时默认的 `runs/vibeflow` 与测试缓存不会污染工作树。

完整入口覆盖仓库质量、pytest、Python sandbox、JavaScript integration、真实浏览器、基线规则对照、接口与多文件资源沙箱、wheel 隔离、双发行 smoke、确定性归档及清洁工作树检查。

资源专项使用正式 CLI，覆盖登记、归属、规则、修改、展示和原生运行。单独重跑见[sandbox/resources](../../sandbox/resources/README.md)；稳定案例与历史验收分别见[案例对应表](../design/multifile-resource-cases.md)和[实现验收记录](../design/multifile-resources-results.md)。

仓库自检器为：

```bash
python quality/run.py --profile all
```

它检查目录、依赖方向、Target 隔离、生成物、文档链接和发行源。用户项目使用 `python -m vibeflow quality-check` 或发行包装器的 `quality`。

## 文档维护

- `docs/user/` 面向业务项目的开发者与 AI，说明如何声明、启用、检查、构建和查看资源；
- `distribution/prompts/` 为 AI 提供任务导航和 profile 协议，链接使用手册中的完整规范；
- `docs/design/` 的系统架构与执行模型解释当前内核，阶段计划和验收保留对应基线及证据；
- `docs/maintainers/` 面向内核开发者，记录修改、验证和发行操作；
- 同一规范在一个位置完整定义，其他文档链接到对应主题；
- 示例按公开 SDK 与实际 schema 编写，加载边界在相关操作处说明；
- 优先描述操作及结果，必要限制准确定位到适用场景。历史计划标注后续方案，冻结报告保留原观察。

修改文档后运行文档一致性与可执行示例测试，再按[发行装配](release.md)构建两个包。检查生成 AGENTS 的阅读入口、复制后的链接和公开示例，分别核对内容正确性与包内字节一致性。
