from __future__ import annotations

import argparse
from pathlib import PurePosixPath


def add_quality_limit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-lines", type=int, default=500, help="maximum source file lines before error")
    parser.add_argument("--warn-lines", type=int, default=450, help="source file lines before warning")
    parser.add_argument("--max-bytes", type=int, default=60000, help="maximum source file bytes before error")
    parser.add_argument("--max-file-branches", type=int, default=150, help="maximum source file branch count before warning")
    parser.add_argument("--max-directory-fanout", type=int, default=25, help="maximum directory fanout before warning")
    parser.add_argument("--max-directory-fanin", type=int, default=25, help="maximum directory fanin before warning")
    parser.add_argument("--max-prefix-cluster-files", type=int, default=12, help="maximum same-prefix files before package warning")
    parser.add_argument("--max-public-entry-bypass-imports", type=int, default=3, help="maximum direct internal imports from one cluster before warning")
    parser.add_argument("--max-dependency-distance", type=int, default=3, help="maximum module path distance before warning")
    parser.add_argument("--max-scattered-dependency-directories", type=int, default=6, help="maximum far dependency directories before warning")
    parser.add_argument("--max-function-lines", type=int, default=80, help="maximum function lines before warning")
    parser.add_argument("--max-function-branches", type=int, default=12, help="maximum function branch count before warning")
    parser.add_argument("--max-function-nesting", type=int, default=4, help="maximum function nesting depth before warning")
    parser.add_argument("--max-function-params", type=int, default=6, help="maximum function parameter count before warning")
    parser.add_argument("--warn-dependency-depth", type=int, default=6, help="dependency chain length before warning")
    parser.add_argument("--max-dependency-depth", type=int, default=10, help="dependency chain length before error")
    _add_structure_arguments(parser)
    parser.add_argument("--include-references", action="store_true", help="also scan references/ directories")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        type=_directory_name,
        metavar="NAME",
        help="exclude a top-level directory relative to each scan root; repeatable",
    )
    parser.add_argument(
        "--exclude-path",
        action="append",
        default=[],
        type=_root_relative_path,
        metavar="PATH",
        help="exclude an exact root-relative file or directory; repeatable",
    )


def _add_structure_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enable-structure-limits", action="store_true", help="enable root structure limits for --path scans")
    parser.add_argument("--no-structure-limits", action="store_true", help="disable workspace/root structure limits")
    parser.add_argument("--warn-root-code-files", type=int, default=None, help="root source file count before warning")
    parser.add_argument("--max-root-code-files", type=int, default=None, help="root source file count before error")
    parser.add_argument("--warn-code-dirs", type=int, default=None, help="code directory count before warning")
    parser.add_argument("--max-code-dirs", type=int, default=None, help="code directory count before error")
    parser.add_argument("--warn-code-files-per-dir", type=int, default=None, help="direct source files per directory before warning")
    parser.add_argument("--max-code-files-per-dir", type=int, default=None, help="direct source files per directory before error")
    parser.add_argument("--warn-code-dir-depth", type=int, default=None, help="code directory depth before warning")
    parser.add_argument("--max-code-dir-depth", type=int, default=None, help="code directory depth before error")
    parser.add_argument("--warn-child-code-dirs-per-dir", type=int, default=None, help="direct child code directories before warning")
    parser.add_argument("--max-child-code-dirs-per-dir", type=int, default=None, help="direct child code directories before error")
    parser.add_argument("--warn-root-level-code-files", type=int, default=None, help="non-allowlisted top-level source files before warning")
    parser.add_argument("--max-root-level-code-files", type=int, default=None, help="non-allowlisted top-level source files before error")


def _directory_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
    ):
        raise argparse.ArgumentTypeError(
            "directory name must be one non-empty path component"
        )
    return name


def _root_relative_path(value: str) -> str:
    raw = value.strip()
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise argparse.ArgumentTypeError(
            "excluded path must be a non-empty root-relative POSIX path"
        )
    return path.as_posix()


def _quality_thresholds(args: argparse.Namespace, threshold_cls):
    return threshold_cls(
        max_file_lines=args.max_lines,
        warn_file_lines=args.warn_lines,
        max_file_bytes=args.max_bytes,
        max_file_branches=args.max_file_branches,
        max_directory_fanout=args.max_directory_fanout,
        max_directory_fanin=args.max_directory_fanin,
        max_prefix_cluster_files=args.max_prefix_cluster_files,
        max_public_entry_bypass_imports=args.max_public_entry_bypass_imports,
        max_dependency_distance=args.max_dependency_distance,
        max_scattered_dependency_directories=args.max_scattered_dependency_directories,
        max_function_lines=args.max_function_lines,
        max_function_branches=args.max_function_branches,
        max_function_nesting=args.max_function_nesting,
        max_function_params=args.max_function_params,
        warn_dependency_chain=args.warn_dependency_depth,
        max_dependency_chain=args.max_dependency_depth,
    )



def _quality_structure_enabled(args: argparse.Namespace, has_overrides: bool) -> bool | None:
    if args.no_structure_limits:
        return False
    if args.enable_structure_limits or has_overrides:
        return True
    return None


def _quality_structure_overrides(args: argparse.Namespace) -> dict[str, object]:
    fields = (
        "warn_root_code_files",
        "max_root_code_files",
        "warn_code_dirs",
        "max_code_dirs",
        "warn_code_files_per_dir",
        "max_code_files_per_dir",
        "warn_code_dir_depth",
        "max_code_dir_depth",
        "warn_child_code_dirs_per_dir",
        "max_child_code_dirs_per_dir",
        "warn_root_level_code_files",
        "max_root_level_code_files",
    )
    return {field: getattr(args, field) for field in fields if getattr(args, field) is not None}
