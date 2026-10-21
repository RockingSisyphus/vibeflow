"""Python file discovery and source-quality facts, without Rule execution."""
from pathlib import Path
from typing import Iterable
from vibeflow.targets.python.quality.source import PythonSource, analyze_python_source
from vibeflow.targets.shared.quality_support import SourceQualityFacts

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "distribution",
        "node_modules",
        "references",
        "site-packages",
        "tests",
        "vendor",
        "venv",
        "vibeflow_distribution",
        "./sandbox/python/integration",
        "./sandbox/javascript/integration",
    }
)

def _iter_python_files(
    root: Path,
    excluded_dirs: set[str],
) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".py":
        if not _skip_file(root):
            yield root
        return
    anywhere, rooted = _split_excluded_dirs(excluded_dirs)
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(part in anywhere for part in relative.parts):
            continue
        if any(relative == item or item in relative.parents for item in rooted):
            continue
        if not _skip_file(path):
            yield path

def _split_excluded_dirs(
    excluded_dirs: set[str],
) -> tuple[set[str], tuple[Path, ...]]:
    anywhere = {item for item in excluded_dirs if not item.startswith("./")}
    rooted = tuple(
        Path(item[2:])
        for item in sorted(excluded_dirs)
        if item.startswith("./") and item[2:]
    )
    return anywhere, rooted

def _skip_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".generated.py", "_pb2.py", "_pb2_grpc.py")) or name in {
        "build_distribution.py",
        "credentials.py",
        "secrets.py",
    }

def _relative_path(root: Path, path: Path) -> str:
    if root.is_file():
        return path.name
    return path.relative_to(root).as_posix()

def _module_name(root: Path, path: Path) -> str:
    if root.is_file():
        return path.stem
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or path.stem

def collect_root_source_facts(root, *, excluded_dirs=DEFAULT_EXCLUDED_DIRS, parse_cache=None):
    root = Path(root).resolve()
    files, findings = [], []
    for path in _iter_python_files(root, set(excluded_dirs)):
        source = PythonSource(_module_name(root, path), _relative_path(root, path), str(path), path.read_text(encoding="utf-8"))
        measured = analyze_python_source(source, _parse_cache=parse_cache)
        files.append(measured.file)
        findings.extend(measured.findings)
    return SourceQualityFacts(str(root), tuple(files), tuple(findings))
