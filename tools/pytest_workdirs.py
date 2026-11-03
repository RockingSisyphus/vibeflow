"""Keep each pytest-xdist worker's runtime artifacts in its own directory."""

import os
from pathlib import Path


def external_scratch(path: Path, repository: Path) -> Path:
    """Keep disposable test workspaces out of maintained repository trees."""
    resolved = path.expanduser().resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("test scratch must be outside the repository; omit --scratch for automatic cleanup")
    return resolved


def pytest_configure(config):
    worker_input = getattr(config, "workerinput", None)
    # The xdist controller launches workers with the original pytest arguments.
    # Keep its invocation directory until those workers parse their targets;
    # only workers collect and execute tests in a parallel run.
    if not worker_input and config.getoption("numprocesses", default=0):
        return
    # Pytest has already distinguished positional targets from option values.
    # Preserve those targets before moving collection and execution away from
    # the invocation directory. Module names for --pyargs remain module names.
    if not config.getoption("pyargs"):
        targets = []
        for argument in config.args:
            filename, *selection = argument.split("::", 1)
            targets.append(str(Path(filename).resolve()) + ("::" + selection[0] if selection else ""))
        config.args[:] = targets
    worker = worker_input["workerid"] if worker_input else "main"
    directory = Path(os.environ["VIBEFLOW_PYTEST_WORK_ROOT"]) / worker
    directory.mkdir(parents=True, exist_ok=True)
    os.chdir(directory)
