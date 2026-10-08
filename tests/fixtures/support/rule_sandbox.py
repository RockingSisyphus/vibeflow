"""Copy a runnable graph with fixed SDK declarations for regression."""
from tests.fixtures.support.plugins import resource as resource_ref, copy_sdk_inputs

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RuleGraphSandbox:
    target: str
    root: Path

    @property
    def project(self):
        return self.root / "project"

    @property
    def workspace(self):
        return self.root / "vibeflow_config.jsonc"

    @property
    def config(self):
        return self.project / "configs/calculate.jsonc"

    @property
    def marker(self):
        return self.root / "rule-events.jsonl"

    @property
    def graph_resource(self):
        return resource_ref(self.project, 'ruleset', 'example.rule_graph')

    def read(self, path):
        return json.loads(path.read_text())

    def write(self, path, document):
        path.write_text(json.dumps(document, indent=2) + "\n")

    def events(self):
        return [json.loads(line) for line in self.marker.read_text().splitlines()] if self.marker.exists() else []

    def common_arguments(self):
        return ["--workspace", str(self.workspace), "--config", str(self.config)]


def create_rule_graph_sandbox(tmp_path, target, *, toolchain_root=None):
    """Return a self-contained project using real external Rule handlers.

    Node arithmetic does not depend on the audit records. Tests can therefore
    distinguish successful auditing from successful business execution.
    """
    root = tmp_path / target
    shutil.copytree(ROOT / "sandbox" / target / "rule_graph", root)
    copy_sdk_inputs(ROOT / "sandbox" / target / "rule_graph", root)
    sandbox = RuleGraphSandbox(target, root)
    if target == "javascript":
        toolchain = Path(toolchain_root or os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
        if not (toolchain / "node_modules").is_dir():
            raise FileNotFoundError("Rule graph sandbox requires the JavaScript test toolchain")
        (sandbox.project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    else:
        sys.modules.pop("rule_graph_nodes", None)
    for name in ("provider", "checker", "replacement", "wrong-replacement"):
        rule_id = {"provider": "number_provider", "checker": "number_checker", "replacement": "replacement_provider", "wrong-replacement": "wrong_provider"}[name]
        path = resource_ref(sandbox.project, "rule", "example." + rule_id)
        data = sandbox.read(path)
        data["params_defaults"]["marker"] = str(sandbox.marker)
        if name != "checker":
            data["params_defaults"]["source"] = str(sandbox.project / "rules" / ("provider.py" if target == "python" else "provider.ts"))
        sandbox.write(path, data)
    return sandbox
