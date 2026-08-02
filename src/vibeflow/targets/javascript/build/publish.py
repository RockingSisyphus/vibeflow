from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RENAME_EXCHANGE = 2
_AT_FDCWD = -100
_MANIFEST_KEYS = frozenset(
    {
        "format",
        "abi_version",
        "project_target",
        "workflow_id",
        "entry_mode",
        "target",
        "profile",
        "entry",
        "plan_sha256",
        "toolchain",
        "external_packages",
        "host_extensions",
        "files",
    }
)
_OPTIONAL_MANIFEST_KEYS = frozenset(
    {"plugin_abi_version", "plugins"}
)
_TOOLCHAIN_KEYS = frozenset(
    {"node", "typescript", "esbuild", "lock_sha256", "lock_files"}
)


class AotPublishError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def validate_owned_build_directory(
    directory: str | Path,
    *,
    manifest_format: str,
) -> Mapping[str, Any]:
    """Verify that a replace target is exactly one intact AOT build."""

    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            f"output target is not a regular directory: {root}",
        )
    manifest_path = root / "vibeflow-build.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            "refusing to replace a directory without a regular VibeFlow AOT manifest",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            "refusing to replace a directory with an unreadable VibeFlow AOT manifest",
        ) from exc
    if not isinstance(manifest, Mapping):
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            "VibeFlow AOT manifest must be a JSON object",
        )
    manifest_keys = set(manifest)
    if (
        not _MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(
            _MANIFEST_KEYS | _OPTIONAL_MANIFEST_KEYS
        )
        or (("plugins" in manifest) != ("plugin_abi_version" in manifest))
    ):
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            "VibeFlow AOT manifest fields do not match the current format",
        )
    if manifest.get("format") != manifest_format:
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            "refusing to replace a directory not owned by this VibeFlow AOT format",
        )
    _require_text(manifest, "abi_version")
    if manifest.get("project_target") != "javascript":
        _invalid_manifest("project_target must be 'javascript'")
    _require_text(manifest, "workflow_id")
    if "plugin_abi_version" in manifest:
        if manifest.get("plugin_abi_version") != "vibeflow.plugin.v1":
            _invalid_manifest("plugin_abi_version is invalid")
        _validate_plugins(manifest.get("plugins"))
    if manifest.get("entry_mode") not in {"sync", "async"}:
        _invalid_manifest("entry_mode must be 'sync' or 'async'")
    if manifest.get("target") not in {"browser", "node"}:
        _invalid_manifest("target must be 'browser' or 'node'")
    if manifest.get("profile") not in {
        "esm-module",
        "single-esm",
        "web-app",
    }:
        _invalid_manifest("profile is invalid")
    plan_hash = manifest.get("plan_sha256")
    if not isinstance(plan_hash, str) or not _SHA256_RE.fullmatch(plan_hash):
        _invalid_manifest("plan_sha256 is invalid")
    external = manifest.get("external_packages")
    if (
        not isinstance(external, list)
        or any(not isinstance(item, str) or not item for item in external)
        or external != sorted(set(external))
    ):
        _invalid_manifest("external_packages must be sorted unique strings")
    host_extensions = manifest.get("host_extensions")
    if (
        not isinstance(host_extensions, list)
        or any(
            not isinstance(item, str) or not item
            for item in host_extensions
        )
        or len(host_extensions) != len(set(host_extensions))
    ):
        _invalid_manifest(
            "host_extensions must be unique non-empty strings"
        )
    _validate_toolchain(manifest.get("toolchain"))

    raw_files = manifest.get("files")
    if not isinstance(raw_files, Mapping) or not raw_files:
        _invalid_manifest("files must be a non-empty object")
    files: dict[str, str] = {}
    for raw_name, raw_hash in raw_files.items():
        if not isinstance(raw_name, str):
            _invalid_manifest("file names must be strings")
        name = _safe_relative_name(raw_name)
        if name == "vibeflow-build.json":
            _invalid_manifest("manifest must not hash itself")
        if not isinstance(raw_hash, str) or not _SHA256_RE.fullmatch(raw_hash):
            _invalid_manifest(f"file hash is invalid: {name}")
        files[name] = raw_hash
    if len(files) != len(raw_files):
        _invalid_manifest("file names are not canonical and unique")

    entry = manifest.get("entry")
    if not isinstance(entry, str):
        _invalid_manifest("entry must be a string")
    entry = _safe_relative_name(entry)
    if entry not in files:
        _invalid_manifest("entry is not listed in files")

    actual_files, actual_directories = _actual_tree(root)
    expected_files = set(files)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            (
                "refusing to replace a modified AOT directory; "
                f"missing={missing}, untracked={extra}"
            ),
        )
    expected_directories = _expected_directories(expected_files)
    if actual_directories != expected_directories:
        extra = sorted(actual_directories - expected_directories)
        missing = sorted(expected_directories - actual_directories)
        raise AotPublishError(
            "VF_BUILD_REPLACE",
            (
                "refusing to replace an AOT directory with untracked layout; "
                f"missing_dirs={missing}, untracked_dirs={extra}"
            ),
        )
    for name, expected_hash in files.items():
        path = root.joinpath(*PurePosixPath(name).parts)
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise AotPublishError(
                "VF_BUILD_REPLACE",
                f"refusing to replace a modified AOT file: {name}",
            )
    return manifest


def _validate_plugins(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "active",
        "annotations",
        "declared",
        "planned",
        "relaxations",
    }:
        _invalid_manifest("plugins must contain the canonical plugin fields")
    for field in (
        "active",
        "annotations",
        "declared",
        "planned",
        "relaxations",
    ):
        if not isinstance(value.get(field), list):
            _invalid_manifest(f"plugins.{field} must be a list")
    for field in ("active", "declared"):
        for item in value[field]:
            if not isinstance(item, Mapping):
                _invalid_manifest(f"plugins.{field} entries must be objects")
            plugin_id = item.get("id")
            config_hash = item.get("config_hash")
            if not isinstance(plugin_id, str) or not plugin_id:
                _invalid_manifest(f"plugins.{field} plugin id is invalid")
            if (
                not isinstance(config_hash, str)
                or not _SHA256_RE.fullmatch(config_hash)
            ):
                _invalid_manifest(
                    f"plugins.{field} config_hash is invalid"
                )
            if item.get("status") == "implemented":
                source_hash = item.get("source_hash")
                if (
                    not isinstance(source_hash, str)
                    or not _SHA256_RE.fullmatch(source_hash)
                ):
                    _invalid_manifest(
                        f"plugins.{field} source_hash is invalid"
                    )


def atomic_publish_directory(
    staging: str | Path,
    out_dir: str | Path,
    *,
    replace: bool,
    manifest_format: str,
) -> None:
    """Publish a validated directory without a reader-visible missing window."""

    source = Path(staging)
    target = Path(out_dir)
    validate_owned_build_directory(
        source,
        manifest_format=manifest_format,
    )
    target_exists = os.path.lexists(target)
    if not target_exists:
        os.replace(source, target)
        return
    if not replace:
        raise AotPublishError(
            "VF_BUILD_EXISTS",
            f"output directory already exists: {target}",
        )
    validate_owned_build_directory(
        target,
        manifest_format=manifest_format,
    )
    _exchange_directories(source, target)


def _exchange_directories(source: Path, target: Path) -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise AotPublishError(
            "VF_BUILD_ATOMIC_REPLACE",
            (
                "this platform cannot atomically exchange non-empty build "
                "directories; the existing artifact was preserved"
            ),
        )
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise AotPublishError(
            "VF_BUILD_ATOMIC_REPLACE",
            (
                "renameat2(RENAME_EXCHANGE) is unavailable; the existing "
                "artifact was preserved"
            ),
        )
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_EXCHANGE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    reason = os.strerror(error_number)
    hint = ""
    if error_number in {
        errno.ENOSYS,
        errno.EINVAL,
        errno.EXDEV,
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }:
        hint = "; atomic directory exchange is unsupported here"
    raise AotPublishError(
        "VF_BUILD_ATOMIC_REPLACE",
        (
            f"could not atomically exchange build directories: {reason}{hint}; "
            "the existing artifact was preserved"
        ),
    )


def _actual_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    for current, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in tuple(dir_names):
            path = current_path / name
            if path.is_symlink():
                raise AotPublishError(
                    "VF_BUILD_REPLACE",
                    f"AOT build directory contains a symlink: {path}",
                )
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                raise AotPublishError(
                    "VF_BUILD_REPLACE",
                    f"AOT build directory contains a non-regular file: {path}",
                )
            relative = path.relative_to(root).as_posix()
            if relative != "vibeflow-build.json":
                files.add(relative)
    return files, directories


def _expected_directories(files: set[str]) -> set[str]:
    directories: set[str] = set()
    for name in files:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _validate_toolchain(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOOLCHAIN_KEYS:
        _invalid_manifest("toolchain fields are invalid")
    for key in ("node", "typescript", "esbuild"):
        _require_text(value, key)
    lock_hash = value.get("lock_sha256")
    if not isinstance(lock_hash, str) or not _SHA256_RE.fullmatch(lock_hash):
        _invalid_manifest("toolchain.lock_sha256 is invalid")
    lock_files = value.get("lock_files")
    if (
        not isinstance(lock_files, list)
        or not lock_files
        or any(not isinstance(item, str) or not item for item in lock_files)
        or lock_files != sorted(set(lock_files))
    ):
        _invalid_manifest("toolchain.lock_files must be sorted unique strings")


def _safe_relative_name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        _invalid_manifest(f"unsafe or non-canonical file name: {value!r}")
    return value


def _require_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        _invalid_manifest(f"{key} must be a non-empty string")
    return item


def _invalid_manifest(reason: str) -> None:
    raise AotPublishError(
        "VF_BUILD_REPLACE",
        f"invalid VibeFlow AOT manifest: {reason}",
    )


__all__ = [
    "AotPublishError",
    "atomic_publish_directory",
    "validate_owned_build_directory",
]
