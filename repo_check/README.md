# VibeFlow repository quality checker

This directory is a self-contained standard-library Python project. It checks
the VibeFlow repository itself and deliberately does not import `vibeflow`.
It is not included in the VibeFlow wheel or distribution package.

Run all profiles from the repository root:

```bash
python repo_check/run.py --profile all
```

Run one profile or emit the stable JSON report:

```bash
python repo_check/run.py --profile core
python repo_check/run.py --profile javascript-target --format json
```

Profiles are `base`, `core`, `block-compiler`, `python-target`,
`javascript-target`, and `all`. JavaScript checks require Node.js 22 or newer.
Exit status `0` means the selected profile passed, `1` means it found repository
violations, and `2` means the checker could not run (for example, the requested
repository or Node.js executable was missing).

The checker builds an AST import graph for every module under `src/vibeflow`.
Imports at module scope, inside functions, under `TYPE_CHECKING`, and fixed-string
`importlib.import_module()`/`__import__()` calls are included. Python and
JavaScript profiles also follow their application entry-point closures and
report the shortest path to a cross-Target dependency. The base profile keeps
shared Tooling and CLI code Target-neutral; explicit Target application entry
points are the only boundary it may dispatch through.

The checker's own tests use only `unittest`. The runner also prevents test
bytecode from being written into the source tree:

```bash
python repo_check/test.py
```

## 目录用途与边界

仅用于：VibeFlow 仓库自身的独立质检工具及其测试；不属于产品 Rule，不进入 wheel 或发行包。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
