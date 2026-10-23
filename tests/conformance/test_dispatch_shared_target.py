import asyncio

def _execute(runtime,*args,**kwargs):
    return asyncio.run(runtime.run_async(*args,**kwargs)) if runtime.graph.entry_mode == 'async' else runtime.run(*args,**kwargs)

"""A shared ordinary call must respect every dispatch that activated it."""

import subprocess
from threading import Event

from tests.conformance.test_dispatch_concurrency import _background
from tests.conformance.test_graph_concurrency import _call
from tests.fixtures.support.declarations import native_registry
from tests.targets.javascript.aot_fixtures import emit_fixture
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.tooling.project.graph_config import parse_graph_config


EDGES = [("start", "left"), ("start", "right"), ("left", "a"), ("left", "shared"),
         ("right", "b"), ("right", "shared"), ("a", "end"), ("b", "end"), ("shared", "end")]


def test_python_shared_call_respects_both_dispatch_limits(tmp_path):
    entered_a, entered_b, done_a, shared = Event(), Event(), Event(), Event()
    release_a, release_b = Event(), Event()

    class Empty:
        def run_pure(self, inputs, params): return {}

    class Right:
        def run_pure(self, inputs, params):
            assert entered_a.wait(5)
            return {}

    class A:
        def run_pure(self, inputs, params):
            entered_a.set()
            assert release_a.wait(10)
            done_a.set()
            return {}

    class B:
        def run_pure(self, inputs, params):
            entered_b.set()
            assert release_b.wait(10)
            return {}

    class Shared:
        def run_pure(self, inputs, params):
            shared.set()
            return {}

    registry = native_registry()
    implementations = {"start": Empty, "left": Empty, "right": Right, "a": A, "b": B, "shared": Shared, "end": Empty}
    nodes = []
    for name, implementation in implementations.items():
        registry.register(NodeDescriptor("shared." + name, name, name, "1",
            "terminal" if name in {"start", "end"} else "process",
            contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"), implementation)
        nodes.append(_call(name, "shared." + name,
            **({"config": {"max_concurrency": 1}} if name in {"left", "right"} else {}),
            join_policy="all" if name == "end" else "any_active"))
    graph = parse_graph_config({"pipeline": {'entry_mode': 'async', "nodes": nodes, "edges": EDGES}})
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path)
    thread, errors = _background(runtime)
    try:
        assert entered_b.wait(5)
        release_a.set()
        assert done_a.wait(5)
        assert not shared.wait(.2), "shared call bypassed the right dispatch's occupied slot"
    finally:
        release_a.set()
        release_b.set()
        thread.join(10)
    assert not thread.is_alive() and not errors, errors
    assert shared.is_set() and runtime.trace.node_runs["shared"] == 1


def test_javascript_shared_call_respects_both_dispatch_limits(tmp_path):
    nodes = []
    for name in ("start", "left", "right", "a", "b", "shared", "end"):
        nodes.append(dict(id=name, definition_id="shared." + name,
            flow_kind="terminal" if name in {"start", "end"} else "process",
            is_terminal=name in {"start", "end"}, join_policy="all" if name == "end" else "any_active",
            max_concurrency=1 if name in {"left", "right"} else 8,
            completion="suspend" if name in {"right", "a", "b"} else "immediate",
            implementation={"kind": "file", "ref": "./nodes.mjs", "export": name if name not in {"start", "left", "end"} else "empty"}))
    (tmp_path / "workflow.mjs").write_text(emit_fixture({"entry_mode": "async", "nodes": nodes,
        "routes": [dict(source=source, target=target) for source, target in EDGES]}).source)
    (tmp_path / "nodes.mjs").write_text('''
export const state={a:false,b:false,doneA:false,shared:false};
let beganA;
const enteredA=new Promise(resolve=>beganA=resolve);
export function empty(){return {};}
export async function right(){await enteredA;return {};}
export async function a(){state.a=true;beganA();await new Promise(resolve=>state.releaseA=resolve);state.doneA=true;return {};}
export async function b(){state.b=true;await new Promise(resolve=>state.releaseB=resolve);return {};}
export function shared(){state.shared=true;return {};}
''')
    (tmp_path / "run.mjs").write_text('''
import {runWorkflowAsync} from './workflow.mjs';
import {state} from './nodes.mjs';
const pending=runWorkflowAsync({});
async function until(test){const deadline=Date.now()+5000;while(!test()){if(Date.now()>deadline)throw Error('stalled');await new Promise(r=>setImmediate(r));}}
await until(()=>state.b);state.releaseA();await until(()=>state.doneA);
for(let turn=0;turn<20;turn++)await new Promise(r=>setImmediate(r));
if(state.shared)throw Error('shared call bypassed the right dispatch slot');
state.releaseB();await pending;
if(!state.shared)throw Error('shared call was lost');
console.log('PASS');
''')
    result = subprocess.run(["node", str(tmp_path / "run.mjs")], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"
