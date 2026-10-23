"""Packaged resources owned by the JavaScript Target."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from contextlib import contextmanager
from pathlib import Path
import tempfile


RESOURCE_NAMES = frozenset(
    {
        "capability_helpers.mjs", "plugin_helpers.mjs", "root_helpers.mjs",
        "coordination/contracts.mjs", "coordination/coordinator.mjs", "coordination/workflow_client.mjs", "coordination/workflow_host.mjs", "coordination/workflow_node.mjs",
        "runtime_helpers.mjs", "execution_helpers.mjs", "status_helpers.mjs", "node_observation.mjs",
        "sdk.mjs", "sdk.d.ts", "sdk_loader.mjs", "node_declarations.mjs", "node_contracts.d.ts",
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
            destination = path / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(directory.joinpath(name).read_bytes())
        yield path


__all__ = ["RESOURCE_NAMES", "read_text", "resource", "materialized_resources"]


def coordination_contract_source():
    """Generate the portable coordination constants from Core declarations."""
    import json
    from vibeflow.core.workflows.coordination import TERMINAL, STATES
    from vibeflow.core.workflows.interfaces import WORKFLOW_OPERATIONS
    values = {"terminalStates": sorted(TERMINAL), "states": list(STATES), "operations": sorted(WORKFLOW_OPERATIONS)}
    return "// Generated from core.workflows contracts.\n" + "".join(
        f"export const {name} = {json.dumps(value)};\n" for name, value in values.items())
