# 通用 quality-check 当前状态

## 结论

`quality-check` 现在已移除针对本仓库主体 `a` 的专属 `--self` 模式。工具只通过 `--path` 检查传入的 Python 项目或文件。

当前定位：

- 默认检查通用代码质量、依赖图和结构启发式。
- 不再内置 `vibeflow` 专属架构规则。
- 不再内置本仓库专属副作用 allowlist。
- 副作用检查改为显式 opt-in，避免普通 Python 项目因为 CLI、测试、构建脚本读写文件而产生大量默认噪声。

## 当前命令

默认通用检查：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

显式检查副作用 API：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path . --check-side-effects
```

## 已移除的 a 专属能力

- `quality-check --self`
- `self_check` 参数链
- `vibeflow` core/devtools/CLI 分层 hardcode
- production/tests hardcode
- 本仓库专属 side-effect allowlist

## 已保留并通用化的能力

- 文件大小、函数大小、分支数、嵌套深度。
- import cycle、双向依赖、依赖链长度。
- duplicate AST fingerprint。
- 目录图和结构摘要。
- 同前缀功能簇识别。
- 内部模块命名启发式。
- 公共入口绕过启发式。
- 依赖距离与分散依赖启发式。
- 结构迁移建议写入 finding details。
- Path-like 副作用识别，但需要 `--check-side-effects` 显式启用。

## 验证结果

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

结果：`PASS`，99 files，0 errors，0 warnings。

```bash
PYTHONPATH=src python3 -m pytest -q
```

结果：166 passed。
