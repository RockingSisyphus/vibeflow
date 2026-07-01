# 文件结构质量检查进度

## 当前状态

已完成通用化调整：

- 移除本仓库专属自检模式。
- 移除本仓库专属架构 hardcode。
- 移除本仓库专属副作用 allowlist。
- 保留并通用化目录图、功能簇、内部模块、公共入口、依赖距离和结构建议。
- 将副作用 API 检查改为显式 opt-in。

## 当前验证

默认通用检查：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path .
```

结果：

```text
PASS
files=84
errors=0
warnings=0
```

显式副作用检查：

```bash
PYTHONPATH=src python3 -m vibeflow quality-check --path . --check-side-effects
```

结果：

```text
CONCERNS
errors=0
warnings=127
```

这说明副作用规则仍可用，但不作为普通项目默认噪声。

## 测试

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

结果：149 passed。
