"""Minimal public-SDK array-default registration reproduction."""

from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "src"))

from vibeflow.targets.python import NodeRegistry
from vibeflow.targets.python.sdk import Plugin, node


@node(
    type_key="probe.array_default",
    contract={
        "params_schema": {"value": {"type": "array"}},
        "params_defaults": {"value": []},
    },
    rulesets=["vibeflow.process"],
)
class ArrayDefault:
    def run_pure(self, inputs, params):
        return {}


plugin = Plugin(id="probe.array_default", resources=[ArrayDefault])
descriptor = plugin.contributions().resources[0].descriptor


def main():
    print("SDK default type:", type(descriptor.contract.params_defaults["value"]).__name__, flush=True)
    NodeRegistry().register(descriptor, ArrayDefault)
    print("PASS: registered array default")


if __name__ == "__main__":
    main()
