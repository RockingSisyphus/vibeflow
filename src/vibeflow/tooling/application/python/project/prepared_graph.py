"""Internal results retained across one Python preparation/check boundary."""

from dataclasses import dataclass

from vibeflow.core.findings import HealthReport
from vibeflow.core.models import CoreCompilation
from vibeflow.tooling.application.python.project.resource_bindings import PythonResources


@dataclass
class PreparedWorkspaceGraph:
    document: object
    graph: object
    compilation: CoreCompilation
    resources: PythonResources
    plugin_registry: object
    effective_policy: object
    warnings: tuple
    health: HealthReport | None = None

    @property
    def compiled(self):
        return self.compilation.compiled_graph
