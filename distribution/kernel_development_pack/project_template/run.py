from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
KERNEL_ROOT = ROOT / "kernel"
MANIFEST_PATH = KERNEL_ROOT / "MANIFEST.sha256"
KERNEL_ARCHIVE_PATH = KERNEL_ROOT / "vibeflow-kernel.zip"
# Treat unpacked kernel sources and shipped kernel docs as protected so AI work stays focused on project/.
PROTECTED_DIRS = (
    "kernel/docs",
    "kernel/vibeflow",
)
PROTECTED_PREFIXES = tuple(f"{path}/" for path in PROTECTED_DIRS)
PROTECTED_FILES = {
    "run.py",
    "kernel/README.md",
    "kernel/vibeflow-kernel.zip",
    "kernel/THIRD_PARTY_NOTICES.md",
    "kernel/tools/mermaid-renderer/package.json",
    "kernel/tools/mermaid-renderer/package-lock.json",
}
GENERATED_PREFIXES = (
    "kernel/tools/mermaid-renderer/node_modules/",
)


class KernelIntegrityError(RuntimeError):
    def __init__(self, *, changed: list[str], missing: list[str], unexpected: list[str]) -> None:
        super().__init__("kernel integrity check failed")
        self.changed = changed
        self.missing = missing
        self.unexpected = unexpected


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_protected_relative(relative: str) -> bool:
    return relative in PROTECTED_FILES or any(relative.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _is_generated_relative(relative: str) -> bool:
    path = Path(relative)
    return (
        any(relative.startswith(prefix) for prefix in GENERATED_PREFIXES)
        or "__pycache__" in path.parts
        or path.name.endswith(".pyc")
    )


def _iter_protected_files() -> list[str]:
    paths: list[str] = []
    for relative in PROTECTED_FILES:
        if (ROOT / relative).is_file():
            paths.append(relative)
    if KERNEL_ARCHIVE_PATH.is_file():
        paths.append(KERNEL_ARCHIVE_PATH.relative_to(ROOT).as_posix())
    for relative_dir in PROTECTED_DIRS:
        root = ROOT / relative_dir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if path.is_file() and not _is_generated_relative(relative):
                paths.append(relative)
    return sorted(set(paths))


def _read_manifest() -> dict[str, str]:
    if not MANIFEST_PATH.is_file():
        raise KernelIntegrityError(changed=[], missing=[MANIFEST_PATH.relative_to(ROOT).as_posix()], unexpected=[])
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(MANIFEST_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise KernelIntegrityError(
                changed=[f"{MANIFEST_PATH.relative_to(ROOT).as_posix()}:{line_number}"],
                missing=[],
                unexpected=[],
            ) from exc
        entries[relative] = digest
    return entries


def _verify_kernel_manifest() -> None:
    entries = _read_manifest()
    changed: list[str] = []
    missing: list[str] = []
    unexpected: list[str] = []
    for relative, expected in entries.items():
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
        elif _hash_file(path) != expected:
            changed.append(relative)
    recorded = set(entries)
    for relative in _iter_protected_files():
        if _is_protected_relative(relative) and relative not in recorded:
            unexpected.append(relative)
    if changed or missing or unexpected:
        raise KernelIntegrityError(changed=changed, missing=missing, unexpected=unexpected)


def _format_integrity_error(exc: KernelIntegrityError) -> str:
    lines = [
        "KERNEL INTEGRITY CHECK FAILED",
        "",
        "A distributed kernel asset or launcher file was modified.",
        "This may mean an AI or developer changed kernel rules, docs, tools, or notices that are meant to be read-only.",
        "",
    ]
    for title, items in (("Changed", exc.changed), ("Missing", exc.missing), ("Unexpected", exc.unexpected)):
        if items:
            lines.append(f"{title}:")
            lines.extend(f"- {item}" for item in sorted(items))
            lines.append("")
    lines.append("Rebuild or restore the distribution from a trusted source.")
    return "\n".join(lines)


def _run_integrity_check() -> None:
    try:
        _verify_kernel_manifest()
    except KernelIntegrityError as exc:
        print(_format_integrity_error(exc), file=sys.stderr)
        raise SystemExit(2) from exc


_run_integrity_check()
sys.path.insert(0, str(KERNEL_ARCHIVE_PATH))
sys.path.insert(0, str(ROOT))

from vibeflow.cli import main as kernel_cli_main  # noqa: E402


WORKSPACE_CONFIG_PATH = ROOT / "vibeflow_config.jsonc"
COMMAND_ALIASES = {
    "architecture": "export-architecture",
    "ascii": "export-ascii",
    "mermaid": "export-mermaid",
    "quality": "quality-check",
    "svg": "export-svg",
}
WORKSPACE_COMMANDS = {
    "delegate-cli",
    "export-architecture",
    "export-ascii",
    "export-mermaid",
    "export-svg",
    "inspect-config",
    "quality-check",
    "review",
    "run",
    "validate",
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "verify-kernel":
        print("kernel integrity: OK")
        return 0
    kernel_args = _kernel_cli_args(args)
    # delegate-cli installs the selected workspace roots only after its run
    # directory and private diagnostic sink exist.  Preloading here would both
    # leak core diagnostics and let the distribution's default workspace shadow
    # an explicitly selected workspace.
    if not kernel_args or kernel_args[0] != "delegate-cli":
        _prepare_workspace_import_paths(kernel_args)
    return kernel_cli_main(kernel_args)


def _kernel_cli_args(args: list[str]) -> list[str]:
    if not args:
        return args
    command = COMMAND_ALIASES.get(args[0], args[0])
    kernel_args = [command, *args[1:]]
    passthrough_at = kernel_args.index("--") if "--" in kernel_args else len(kernel_args)
    kernel_options = kernel_args[1:passthrough_at]
    has_workspace = any(
        value == "--workspace" or value.startswith("--workspace=")
        for value in kernel_options
    )
    if WORKSPACE_CONFIG_PATH.is_file() and command in WORKSPACE_COMMANDS and not has_workspace:
        kernel_args[1:1] = ["--workspace", str(WORKSPACE_CONFIG_PATH)]
    return kernel_args


def _prepare_workspace_import_paths(args: list[str]) -> None:
    workspace_path = _selected_workspace_path(args)
    if workspace_path is None or not workspace_path.is_file():
        return
    try:
        from vibeflow.workspace import load_workspace_config

        workspace = load_workspace_config(workspace_path)
    except Exception:
        return
    for root in reversed(workspace.roots):
        value = str(root.path)
        if value not in sys.path:
            sys.path.insert(0, value)


def _selected_workspace_path(args: list[str]) -> Path | None:
    passthrough_at = args.index("--") if "--" in args else len(args)
    options = args[1:passthrough_at]
    selected: Path | None = None
    explicit = False
    index = 0
    while index < len(options):
        value = options[index]
        if value == "--workspace":
            explicit = True
            if index + 1 < len(options) and not options[index + 1].startswith("--"):
                selected = Path(options[index + 1])
                index += 1
        elif value.startswith("--workspace="):
            explicit = True
            raw_path = value.partition("=")[2]
            selected = Path(raw_path) if raw_path else None
        index += 1
    return selected if explicit else WORKSPACE_CONFIG_PATH


if __name__ == "__main__":
    raise SystemExit(main())
