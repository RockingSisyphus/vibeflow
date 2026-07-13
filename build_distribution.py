from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import zipfile
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
    "project/stubs",
)
MANIFEST_RELATIVE = Path("kernel/MANIFEST.sha256")
KERNEL_ZIP_RELATIVE = Path("kernel/vibeflow-kernel.zip")
PROTECTED_FILES = (
    "run.py",
    "kernel/README.md",
    KERNEL_ZIP_RELATIVE.as_posix(),
    "kernel/THIRD_PARTY_NOTICES.md",
    "kernel/tools/mermaid-renderer/package.json",
    "kernel/tools/mermaid-renderer/package-lock.json",
)
PROTECTED_DIRS = (
    "kernel/docs",
    "kernel/vibeflow",
)
CORE_SELF_CHECK_STRUCTURE_ARGS = (
    "--enable-structure-limits",
    "--warn-root-code-files",
    "150",
    "--max-root-code-files",
    "200",
    "--warn-code-dirs",
    "16",
    "--max-code-dirs",
    "24",
    "--warn-code-files-per-dir",
    "20",
    "--max-code-files-per-dir",
    "30",
    "--warn-code-dir-depth",
    "4",
    "--max-code-dir-depth",
    "5",
    "--warn-child-code-dirs-per-dir",
    "6",
    "--max-child-code-dirs-per-dir",
    "10",
    "--warn-root-level-code-files",
    "110",
    "--max-root-level-code-files",
    "120",
)


class BuildDistributionError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a copyable VibeFlow distribution directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="directory to rebuild")
    parser.add_argument("--keep-existing", action="store_true", help="fail instead of replacing an existing output directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        build_distribution(output, replace=not args.keep_existing)
    except BuildDistributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"built distribution: {output}")
    return 0


def build_distribution(output: Path, *, replace: bool = True, run_self_check: bool = True) -> None:
    if run_self_check:
        _run_core_self_check()
    _prepare_output(output, replace=replace)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "project_template", output)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "docs", output / "kernel" / "docs")
    _copy_mermaid_renderer_config(output)
    _copy_third_party_notices(output)
    _copy_extra_docs(output / "kernel" / "docs")
    _write_kernel_archive(ROOT / "src" / "vibeflow", output / KERNEL_ZIP_RELATIVE)
    _ensure_standard_project_dirs(output)
    _write_root_readme(output)
    _write_kernel_manifest(output)
    _normalize_output_modes(output)


def _run_core_self_check() -> None:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else os.pathsep.join((src_path, existing_pythonpath))
    command = [sys.executable, "-m", "vibeflow", "quality-check", "--path", "src/vibeflow", *CORE_SELF_CHECK_STRUCTURE_ARGS]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        command_text = " ".join(command)
        raise BuildDistributionError(
            "refusing to build distribution because kernel self-check failed: "
            + f"PYTHONPATH=src {command_text}"
        )


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
    target = output / "kernel" / "tools" / "mermaid-renderer"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        path = source / name
        if path.exists():
            (target / name).write_bytes(path.read_bytes())


def _copy_third_party_notices(output: Path) -> None:
    source = ROOT / "THIRD_PARTY_NOTICES.md"
    if source.exists():
        destination = output / "kernel" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _write_kernel_archive(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            relative_to_package = path.relative_to(source)
            if path.is_dir() or _ignored(relative_to_package):
                continue
            archive_relative = Path("vibeflow") / relative_to_package
            info = zipfile.ZipInfo(archive_relative.as_posix())
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


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


def _normalize_output_modes(output: Path) -> None:
    """Make the directory tree and its deterministic ZIP use identical modes.

    The project is commonly built under a collaborative ``umask 0002``, which
    otherwise leaves generated files at 0664 while the frozen ZIP correctly
    records portable 0644 entries.  Tree hashes include modes, so normalize the
    generated source tree before it is validated or frozen.
    """

    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise BuildDistributionError(
                f"refusing to normalize a distribution containing a symlink: {path}"
            )
        path.chmod(0o755 if path.is_dir() else 0o644)
    output.chmod(0o755)


def _remove_tree(path: Path) -> None:
    for item in sorted(path.rglob("*"), key=lambda candidate: len(candidate.parts), reverse=True):
        if item.is_dir():
            item.rmdir()
        else:
            item.unlink()
    path.rmdir()


def _ignored(relative: Path) -> bool:
    ignored_names = {"__pycache__", ".pytest_cache", "runs", "reports", "node_modules"}
    return any(part in ignored_names or part.endswith(".pyc") for part in relative.parts)


def _write_root_readme(output: Path) -> None:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None:
        generated = datetime.now(timezone.utc)
    else:
        try:
            generated = datetime.fromtimestamp(int(source_date_epoch), timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BuildDistributionError("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    generated_at = generated.strftime("%Y-%m-%d %H:%M:%S UTC")
    text = f"""# VibeFlow 可复制开发包

生成时间：{generated_at}

这个目录可以整体复制到其他位置作为新项目起点。它已经包含：

- `kernel/vibeflow-kernel.zip`：当前仓库最新内核源码归档，`run.py` 会直接从这个单文件导入。
- `kernel/docs/`：内核中文开发文档，可读但不应作为项目内容修改。
- `kernel/tools/mermaid-renderer/`：SVG 渲染器依赖配置；运行 `npm install` 后启用 `svg` 命令。
- `kernel/THIRD_PARTY_NOTICES.md`：SVG 渲染相关第三方项目致谢与许可证信息。
- `project/`：可直接运行的示例业务项目骨架。
- `project/nodes/`、`project/base_lib/`、`project/plugins/`、`project/configs/`：AI 和开发者放业务代码与配置的标准目录。
- `vibeflow_config.jsonc`：workspace 索引，声明参与加载的 source roots。
- `project/vibeflow_project.jsonc`：project 级配置，声明 registry、base_lib、plugins 和 quality 开关。
- `run.py`：推荐启动器，会自动加载本地内核和 workspace 配置。
- `README.md`、`AGENTS.md`：项目可定制指南文件，不属于 kernel manifest。

Runtime 默认审计流程和 key，不保存真实对象内容；node 间可以按引用传递普通 Python 对象。需要指标、日志或诊断 side task 时，在 config 中显式使用 `async: "detached"` 或 `async: "result_key"`。

## 开始使用

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
python run.py quality
```

## Workspace 配置

根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局 policy；每个 root 自己放 `vibeflow_project.jsonc`，声明该 root 的 registry、base_lib、plugins 和 quality 开关。单项目模板默认是：

```jsonc
{{
  "policy": {{}},
  "roots": [
    {{"id": "project", "path": "project"}}
  ]
}}
```

同一个仓库如果要同时放框架层和任务层，可以改成多 root：

```jsonc
{{
  "policy": {{}},
  "roots": [
    {{"id": "vibetrain", "path": "vibetrain"}},
    {{"id": "project", "path": "project"}}
  ]
}}
```

每个 root 下都需要自己的 `vibeflow_project.jsonc`。其中 `registry`、`base_lib.paths` 和 plugin 文件路径都相对所属 root 目录解析。`quality.structure` 使用 warning/error 双阈值治理 root 代码布局，默认允许最多 120 个 `.py`，但单个代码目录超过 16 个 `.py` 会失败，用来推动 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。pipeline config 仍通过 `--config project/configs/main.jsonc` 指定，workspace 模式下不要在 pipeline config 顶层声明 `policy`、`base_lib` 或 `plugins`。

跨 root nodeset import 使用 root id：

```jsonc
{{
  "nodeset_imports": [
    {{"root": "vibetrain", "path": "configs/nodesets/train_step.jsonc"}}
  ]
}}
```

`svg` 默认会为 Mermaid CLI 放大渲染上限：普通图使用 `maxTextSize=200000`、`maxEdges=2000`；`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000`，并固定采用 `review-columns` SVG composer，把主流程、plugins、base_lib 和展开 nodeset 分列展示。超大图可用 `--mermaid-max-text-size` 和 `--mermaid-max-edges` 覆盖。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。详细审查 SVG 必须用 `python run.py svg --expand-nodesets --output reports/graph.expanded.svg` 生成，不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG，否则会绕过 VibeFlow 的 review-columns/detail-panel composer。

首次使用 `svg` 前，在分发目录执行一次：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

## Kernel 完整性检查

分发包包含 `kernel/MANIFEST.sha256`。`run.py` 会在运行前校验 kernel 归档和启动器是否被修改。根目录 `README.md` 和 `AGENTS.md` 是项目指南文件，使用者可以按项目需要自定义。

分发包不内置 `.gitignore`，Git 忽略策略由项目自行决定。常见建议包括忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。

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
- trace 和报告只记录 summary，不序列化 tensor/model/optimizer 等对象。

运行前内核会强制健康检查；检查失败时拒绝执行并输出原因。

更多细节见 `kernel/docs/`。
"""
    (output / "README.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
