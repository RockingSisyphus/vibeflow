"""Internal results retained across one Python preparation/check boundary."""

from dataclasses import dataclass, field

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
    presentation: object | None = field(default=None, init=False, repr=False)

    def presentation_for(self, registry):
        if self.presentation is None:
            from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
            self.presentation = prepare_python_presentation(
                self.graph, registry=registry, resources=self.resources, compilation=self.compilation,
            )
        return self.presentation

    @property
    def compiled(self):
        return self.compilation.compiled_graph
