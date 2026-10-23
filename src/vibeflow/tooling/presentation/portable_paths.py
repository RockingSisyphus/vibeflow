"""Portable paths in saved documents; live diagnostics retain absolute paths."""
from pathlib import Path
from collections.abc import Mapping


def portable_paths(value, *, roots, primary_root):
    # Builtin declarations belong to the installed kernel, including when that
    # kernel is imported from a ZIP rather than the source checkout.
    locations = {"@kernel": Path(__file__).resolve().parents[2], **roots}
    locations = sorted(locations.items(), key=lambda item: len(str(item[1])), reverse=True)

    def visit(item):
        if isinstance(item, Mapping):
            return {visit(key): visit(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [visit(child) for child in item]
        if isinstance(item, str) and Path(item).is_absolute():
            for root_id, root_path in locations:
                try:
                    relative = Path(item).relative_to(root_path).as_posix()
                except ValueError:
                    continue
                prefix = root_id if root_id.startswith("@") else "@" + root_id
                return relative if Path(root_path) == Path(primary_root) else f"{prefix}/{relative}"
        return item

    return visit(value)
