from __future__ import annotations

from vibeflow.core import DataProvider
from vibeflow.targets.python.project import NodeContract, NodeInfo


GLOBAL_STATE_VALUE = "initial"
GLOBAL_STATE_RUNS = 0


def reset_global_state_probe() -> None:
    global GLOBAL_STATE_RUNS, GLOBAL_STATE_VALUE
    GLOBAL_STATE_VALUE = "initial"
    GLOBAL_STATE_RUNS = 0


class GlobalStateProbeNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.global_state_probe",
        display_name="Global State Probe",
        category="sandbox",
        description=(
            "Changes audited process-local ambient state without using any "
            "third-party library."
        ),
        version="0.1.0",
        flow_kind="global_state",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("value.out", "value.out", "Value Out"),),
        output_semantics={
            "value.out": (
                "Number of real runtime invocations; structural examples must "
                "not increment it.",
            )
        },

        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        del inputs, params
        global GLOBAL_STATE_RUNS, GLOBAL_STATE_VALUE
        GLOBAL_STATE_RUNS += 1
        GLOBAL_STATE_VALUE = "configured"
        return {"value.out": GLOBAL_STATE_RUNS}


class GlobalStateFailureNode:
    NODE_INFO = NodeInfo(
        type_key="sandbox.global_state_failure",
        display_name="Global State Failure",
        category="sandbox",
        description="Fails after changing audited process-local ambient state.",
        version="0.1.0",
        flow_kind="global_state",
    )
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        del inputs, params
        global GLOBAL_STATE_VALUE
        GLOBAL_STATE_VALUE = "changed-before-failure"
        raise RuntimeError("sandbox global-state failure")
