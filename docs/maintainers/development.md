# 内核开发与验证

本文面向 VibeFlow 仓库维护者。用户项目开发不需要阅读本页。

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

独立运行 pytest 时必须使用隔离入口，而不是在仓库根目录直接执行 `python -m pytest`：

```bash
python tools/run_tests.py -- tests/core/test_result_scope.py
python tools/run_tests.py
```

该入口在临时工作目录执行测试，固定本仓 `src`、关闭用户站点和自动加载的第三方 pytest 插件，并在结束后移除临时目录。这样运行时默认的 `runs/vibeflow` 与测试缓存不会污染工作树。

完整入口覆盖仓库质量、pytest、Python sandbox、JavaScript integration、wheel 隔离、双发行 smoke、确定性归档和清洁工作树检查。

仓库自检器为：

```bash
python quality/run.py --profile all
```

它检查目录、依赖方向、Target 隔离、生成物、文档链接和发行源。用户项目使用 `python -m vibeflow quality-check` 或发行包装器的 `quality`。

## 文档维护

- `docs/user/` 只记录稳定公共接口和可执行操作；
- `docs/design/` 解释内核结构和语义理由；
- `docs/maintainers/` 记录仓库工作流；
- 同一规范只在一个位置完整定义；
- 迁移历史由 Git 和 release notes 保存；
- 使用者示例以公开导出和实际 schema 为准。

修改文档后运行文档一致性测试和双发行 smoke，确认 AGENTS 路由与复制后的路径有效。
