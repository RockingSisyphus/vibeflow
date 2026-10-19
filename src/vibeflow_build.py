"""Build the standalone viewer's sole source into installed package resources."""
from pathlib import Path
from shutil import copytree
from setuptools.command.build_py import build_py

class ViewerBuild(build_py):
    def run(self):
        super().run()
        source=Path(__file__).parent.parent / "tools" / "workflow-viewer"
        target=Path(self.build_lib) / "vibeflow" / "tooling" / "viewer_assets"
        copytree(source,target,dirs_exist_ok=True)
