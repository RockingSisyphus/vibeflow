"""Portable paths in saved documents; live diagnostics retain absolute paths."""
from pathlib import Path
from collections.abc import Mapping


def portable_paths(value, *, roots, primary_root):
    if isinstance(value, Mapping):
        return {portable_paths(key, roots=roots, primary_root=primary_root): portable_paths(item, roots=roots, primary_root=primary_root) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable_paths(item, roots=roots, primary_root=primary_root) for item in value]
    if isinstance(value, str) and value.startswith("/"):
        for root_id, root_path in sorted(roots.items(), key=lambda item: len(str(item[1])), reverse=True):
            try:
                relative = Path(value).relative_to(root_path).as_posix()
            except ValueError:
                continue
            prefix = root_id if root_id.startswith("@") else "@" + root_id
            return relative if Path(root_path) == Path(primary_root) else f"{prefix}/{relative}"
    return value
