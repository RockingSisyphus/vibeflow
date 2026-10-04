"""Keep each pytest-xdist worker's runtime artifacts in its own directory."""

import os
from pathlib import Path


def pytest_configure(config):
    worker_input = getattr(config, "workerinput", None)
    if worker_input:
        worker = worker_input["workerid"]
        directory = Path(os.environ["VIBEFLOW_PYTEST_WORK_ROOT"]) / worker
        directory.mkdir(parents=True, exist_ok=True)
        os.chdir(directory)
