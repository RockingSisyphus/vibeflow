"""Packaged resources owned by the JavaScript Target."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from contextlib import contextmanager
from pathlib import Path
import tempfile


RESOURCE_NAMES = frozenset(
    {
        "runtime_helpers.mjs", "task_helpers.mjs", "status_helpers.mjs", "node_observation.mjs",
        "sdk.mjs", "sdk.d.ts", "sdk_loader.mjs",
        "plugin_worker.mjs",
        "plugin_abi.d.ts",
        "rule_abi.d.ts",
        "toolchain_driver.mjs", "analysis_program.mjs", "source_ownership.mjs",
    }
)


def resource(name: str) -> Traversable:
    if name not in RESOURCE_NAMES:
        raise ValueError(f"unknown JavaScript Target resource: {name}")
    return files(__package__).joinpath(name)


def read_text(name: str) -> str:
    return resource(name).read_text(encoding="utf-8")


@contextmanager
def materialized_resources():
    """Keep relative SDK imports together, including inside wheel/zip kernels."""
    directory = files(__package__)
    if isinstance(directory, Path):
        yield directory
        return
    with tempfile.TemporaryDirectory(prefix="vibeflow-js-resources-") as temporary:
        path = Path(temporary) / "resources"
        path.mkdir()
        for name in RESOURCE_NAMES:
            (path / name).write_bytes(directory.joinpath(name).read_bytes())
        node_directory = files("vibeflow.targets.javascript.nodetypes")
        node_path = Path(temporary) / "nodetypes"
        node_path.mkdir()
        for name in ("declarations.mjs", "contracts.d.ts"):
            (node_path / name).write_bytes(node_directory.joinpath(name).read_bytes())
        yield path


__all__ = ["RESOURCE_NAMES", "read_text", "resource", "materialized_resources"]
