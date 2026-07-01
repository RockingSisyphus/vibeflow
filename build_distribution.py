from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "vibeflow_distribution"
EXTRA_DOCS = (
    ("developer_guide.md", "10_Kernel能力与项目开发指南.md"),
)
STANDARD_PROJECT_DIRS = (
    "project/nodes",
    "project/base_lib",
    "project/plugins",
    "project/configs",
    "project/configs/nodesets",
)
MANIFEST_RELATIVE = Path("kernel/MANIFEST.sha256")
PROTECTED_FILES = (
    "run.py",
    "kernel/README.md",
    "AGENTS.md",
    "README.md",
)
PROTECTED_DIRS = (
    "kernel/vibeflow",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a copyable VibeFlow distribution directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="directory to rebuild")
    parser.add_argument("--keep-existing", action="store_true", help="fail instead of replacing an existing output directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    build_distribution(output, replace=not args.keep_existing)
    print(f"built distribution: {output}")
    return 0


def build_distribution(output: Path, *, replace: bool = True) -> None:
    _prepare_output(output, replace=replace)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "project_template", output)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "docs", output / "docs")
    _copy_mermaid_renderer_config(output)
    _copy_extra_docs(output / "docs")
    _copy_tree(ROOT / "src" / "vibeflow", output / "kernel" / "vibeflow")
    _ensure_standard_project_dirs(output)
    _write_root_readme(output)
    _write_project_gitignore(output)
    _write_kernel_manifest(output)


def _prepare_output(output: Path, *, replace: bool) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"output already exists: {output}")
    if output.exists():
        _remove_tree(output)
    output.mkdir(parents=True)


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if _ignored(relative):
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())


def _copy_extra_docs(target: Path) -> None:
    for source_name, target_name in EXTRA_DOCS:
        source = ROOT / "docs" / source_name
        destination = target / target_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _copy_mermaid_renderer_config(output: Path) -> None:
    source = ROOT / "tools" / "mermaid-renderer"
    target = output / "tools" / "mermaid-renderer"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        path = source / name
        if path.exists():
            (target / name).write_bytes(path.read_bytes())


def _write_kernel_manifest(output: Path) -> None:
    lines = []
    for relative in _iter_manifest_files(output):
        digest = _hash_file(output / relative)
        lines.append(f"{digest}  {relative.as_posix()}")
    path = output / MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _iter_manifest_files(output: Path) -> list[Path]:
    files: list[Path] = []
    for relative in PROTECTED_FILES:
        path = output / relative
        if path.is_file():
            files.append(Path(relative))
    for relative_dir in PROTECTED_DIRS:
        root = output / relative_dir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(output)
            if path.is_file() and not _ignored(relative):
                files.append(relative)
    return sorted(set(files), key=lambda item: item.as_posix())


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_standard_project_dirs(output: Path) -> None:
    for relative in STANDARD_PROJECT_DIRS:
        (output / relative).mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    for item in sorted(path.rglob("*"), key=lambda candidate: len(candidate.parts), reverse=True):
        if item.is_dir():
            item.rmdir()
        else:
            item.unlink()
    path.rmdir()


def _ignored(relative: Path) -> bool:
    ignored_names = {"__pycache__", ".pytest_cache", "runs", "reports"}
    return any(part in ignored_names or part.endswith(".pyc") for part in relative.parts)


def _write_root_readme(output: Path) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = f"""# VibeFlow 可复制开发包

生成时间：{generated_at}

这个目录可以整体复制到其他位置作为新项目起点。它已经包含：

- `kernel/vibeflow/`：当前仓库最新内核源码副本。
- `docs/`：中文开发文档。
- `project/`：可直接运行的示例业务项目骨架。
- `project/nodes/`、`project/base_lib/`、`project/plugins/`、`project/configs/`：AI 和开发者放业务代码与配置的标准目录。
- `run.py`：推荐启动器，会自动加载本地内核和项目 registry。
- `tools/mermaid-renderer/`：SVG 渲染器依赖配置；运行 `npm install` 后启用 `svg` 命令。

## 开始使用

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py quality --path project
```

首次使用 `svg` 前，在分发目录执行一次：

```powershell
cd tools/mermaid-renderer
npm install
cd ../..
```

## Kernel 完整性检查

分发包包含 `kernel/MANIFEST.sha256`。`run.py` 会在运行前校验 kernel、启动器和 AI 指引文件是否被修改。

手动检查：

```powershell
python run.py verify-kernel
```

如果检查失败，不要继续信任当前分发包；请从可信来源重新生成或恢复。

业务开发原则：

- 只在 `project/nodes/` 写纯函数 node。
- 只在 `project/base_lib/` 写纯 helper。
- 只在 `project/plugins/` 写插件。
- 只用 `project/configs/*.jsonc` 和 nodeset 组织程序结构。
- 控制流必须显式写在 `pipeline.edges` 中。
- 外部输入输出用 `io`、`data_store`、`document` 或 `external=True` node 建模。

运行前内核会强制健康检查；检查失败时拒绝执行并输出原因。

更多细节见 `docs/`。
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def _write_project_gitignore(output: Path) -> None:
    text = """__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
runs/
reports/
*.log
"""
    (output / ".gitignore").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
