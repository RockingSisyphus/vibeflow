"""Give direct verification entrypoints an owning process-tree supervisor."""
import importlib.util
import os
from pathlib import Path
import sys


def entrypoint(script, arguments, main):
    if os.environ.get("VIBEFLOW_PROCESS_SUPERVISED") == "1":
        return main()
    path = Path(__file__).resolve().parents[1] / "src/vibeflow/tooling/application/process_supervisor.py"
    spec = importlib.util.spec_from_file_location("vibeflow_process_supervisor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.supervise([sys.executable, "-B", str(script), *arguments])
