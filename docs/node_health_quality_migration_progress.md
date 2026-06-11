# b* 能力迁移到 node 健康检查进度

## 当前迁移原则

`quality-check` 的仓库结构规则不直接移植到 node 健康检查。node 健康检查只接收与运行安全、纯度、base_lib 可靠性直接相关的能力。

已采用的拆分方式：

- 共享底层 AST 能力放在 `ast_rules.py`。
- node 纯度检查通过 `purity_visitors.py` 使用共享能力。
- base_lib 检查通过 `base_lib.py` 使用共享能力。
- 仓库结构规则仍留在 `devtools/code_quality*.py`。

## 已完成迁移

### Path-like 副作用识别

从 `b*` 迁移到 node/base_lib 健康检查：

- `Path("x").read_text()`
- `path.write_text("x")`
- `(path / "child").open()`
- 其他 `Path` 风格文件 API：
  - `mkdir`
  - `open`
  - `read_bytes`
  - `read_text`
  - `rename`
  - `replace`
  - `rmdir`
  - `touch`
  - `unlink`
  - `write_bytes`
  - `write_text`

实现位置：

- `src/topology_kernel/ast_rules.py`
  - `import_aliases_from_node`
  - `qualified_call_name`
  - `path_effect_call_name`
- `src/topology_kernel/purity_visitors.py`
  - node `run_pure` 纯度检查复用 path-like 副作用识别。
- `src/topology_kernel/base_lib.py`
  - base_lib AST 扫描复用 path-like 副作用识别。
- `src/topology_kernel/devtools/code_quality_rules.py`
  - `quality-check` 自身也改为复用同一套核心 AST 逻辑，避免规则分叉。

## 新增测试

- node 健康检查：
  - `path = Path("x"); path.write_text("bad")`
  - `path = Path("x"); (path / "child").open()`
- base_lib 健康检查：
  - `path.write_text("bad")`
  - `(path / "child").open()`

## 验证结果

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

结果：150 passed。

```bash
PYTHONPATH=src python3 -m topology_kernel quality-check --path .
```

结果：PASS，84 files，0 errors，0 warnings。

```bash
python3 -m compileall -q src tests
```

结果：通过。

```bash
git diff --check -- src/topology_kernel/ast_rules.py src/topology_kernel/base_lib.py src/topology_kernel/purity_visitors.py src/topology_kernel/devtools/code_quality_rules.py tests/unit/test_strict_mermaid_cli.py tests/unit/test_strict_node_purity.py
```

结果：通过。

## 下一批适合迁移的能力

- 更清晰的函数 qualname，可用于 node/base_lib finding 定位。
- 更统一的 import graph 查询接口，可减少 base_lib 与 quality-check 各自维护依赖逻辑。
- 重复逻辑检查的底层 fingerprint 可进一步共享，但需要谨慎避免对合法相似 node 产生噪声。

## 不建议直接迁移的能力

- topology-kernel 自身的架构 contract。
- 目录 fanin/fanout。
- 前缀功能簇 package 化建议。
- 公共入口绕过规则。
- 文件位置与依赖距离规则。

这些属于项目结构维护规则，适合保留在 `quality-check` 或未来的项目级结构健康检查中。
