"""Architecture assembly over prepared facts; no source discovery or execution."""
from .documents import render_architecture_payload
from .workflow import ArchitectureInputs, build_workflow_architecture
from .project import project_architecture, write_project_architecture

__all__ = ["ArchitectureInputs", "build_workflow_architecture", "project_architecture",
           "write_project_architecture", "render_architecture_payload"]
