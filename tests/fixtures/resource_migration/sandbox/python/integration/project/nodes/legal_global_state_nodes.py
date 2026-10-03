from __future__ import annotations
GLOBAL_STATE_VALUE = 'initial'
GLOBAL_STATE_RUNS = 0

def reset_global_state_probe() -> None:
    global GLOBAL_STATE_RUNS, GLOBAL_STATE_VALUE
    GLOBAL_STATE_VALUE = 'initial'
    GLOBAL_STATE_RUNS = 0

class GlobalStateProbeNode:

    def run_pure(self, inputs, params):
        del inputs, params
        global GLOBAL_STATE_RUNS, GLOBAL_STATE_VALUE
        GLOBAL_STATE_RUNS += 1
        GLOBAL_STATE_VALUE = 'configured'
        return {'value.out': GLOBAL_STATE_RUNS}

class GlobalStateFailureNode:

    def run_pure(self, inputs, params):
        del inputs, params
        global GLOBAL_STATE_VALUE
        GLOBAL_STATE_VALUE = 'changed-before-failure'
        raise RuntimeError('sandbox global-state failure')
