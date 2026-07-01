# 通用 quality-check 最终报告

## 结论

`quality-check` 已从“通用工具 + 本仓库专属模式”调整为真正通用的 Python 代码质量检查工具。

当前不再存在针对本仓库主体 `a` 的专属检查入口或 hardcode。

## 接口

默认检查：

```bash
vibeflow quality-check --path <project-or-file>
```

显式副作用检查：

```bash
vibeflow quality-check --path <project-or-file> --check-side-effects
```

## 移除项

- 本仓库专属自检 CLI 参数。
- 本仓库专属架构 contract。
- 本仓库专属副作用 allowlist。
- 生产代码、测试代码、核心层、工具层、CLI 层的 hardcode 关系。

## 保留并通用化的能力

- 文件和函数形状检查。
- 分支和嵌套复杂度检查。
- import graph 检查。
- duplicate fingerprint 检查。
- directory graph。
- prefix cluster。
- public entry bypass。
- distant internal import。
- scattered dependency。
- structure suggestion details。
- opt-in side-effect API 检查。

## 验证结果

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

结果：`PASS`，84 files，0 errors，0 warnings。

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

结果：149 passed。

```bash
python3 -m compileall -q src tests
```

结果：通过。
