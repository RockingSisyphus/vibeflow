"""Python application facade for project-parser diagnostics."""

from vibeflow.tooling.project.diagnostic_sink import (
    core_diagnostic_sink,
    emit_core_diagnostic,
)


__all__ = ["core_diagnostic_sink", "emit_core_diagnostic"]
