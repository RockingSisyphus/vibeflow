import asyncio

def _execute(runtime,*args,**kwargs):
    return asyncio.run(runtime.run_async(*args,**kwargs)) if runtime.graph.entry_mode == 'async' else runtime.run(*args,**kwargs)

"""Per-dispatch admission, incremental refill and actual-exit ownership."""

import subprocess
from threading import Condition, Event, Thread

import pytest

from tests.conformance.test_graph_concurrency import _call
from tests.fixtures.support.declarations import native_registry
from tests.targets.javascript.aot_fixtures import emit_fixture
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.project.graph_config import parse_graph_config


def _python_runtime(tmp_path, groups, make_worker, execution, *, wrapped=False):
    registry = native_registry()

    class Empty:
        def run_pure(self, inputs, params):
            assert "max_concurrency" not in params
            return {}

    for name, kind in (("boundary", "terminal"), ("dispatch", "process")):
        registry.register(NodeDescriptor("budget." + name, name, name, "1", kind,
            contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"), Empty)
    nodes = [_call("start", "budget.boundary")]
    edges = []
    nodeset_types = []
    for group, count, limit in groups:
        options = {} if limit is None else {"config": {"max_concurrency": limit}}
        nodes.append(_call(group, "budget.dispatch", **options))
        edges.append(["start", group])
        for index in range(count):
            name = f"{group}{index}"
            registry.register(NodeDescriptor("budget." + name, name, name, "1", "process",
                contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"), make_worker(group, index))
            target = "budget." + name
            if wrapped:
                body = "budget.body." + name
                nodeset_types.append(dict(type_key=body, display_name=name, description="One queued job",
                    requires=[], provides=[], pipeline=dict(nodes=[_call("start", "budget.boundary"),
                        _call("work", target), _call("end", "budget.boundary")],
                        edges=[["start", "work"], ["work", "end"]])))
                target = body
            nodes.append(_call(name, target))
            edges.extend([[group, name], [name, group + "_join"]])
        nodes.append(_call(group + "_join", "budget.dispatch", join_policy="all"))
        edges.append([group + "_join", "end"])
    nodes.append(_call("end", "budget.boundary", join_policy="all"))
    graph = parse_graph_config({"nodeset_types": nodeset_types, "pipeline": {'entry_mode': 'async', "nodes": nodes, "edges": edges}})
    return PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
        runtime_options=RuntimeOptions(execution=execution))


def _background(runtime):
    errors = []

    def run():
        try:
            _execute(runtime)
        except BaseException as error:
            errors.append(error)

    thread = Thread(target=run)
    thread.start()
    return thread, errors


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
@pytest.mark.parametrize("limit,count,capacity,wrapped", [(None, 12, 8, False), (4, 8, 4, False), (1, 3, 1, False), (4, 8, 4, True)])
def test_python_local_queue_refills_after_real_cleanup(tmp_path, execution, limit, count, capacity, wrapped):
    condition = Condition()
    started, finished = [], []
    active = peak = 0
    first_to_finish = capacity - 1
    release = [Event() for _ in range(count)]
    cleaning, cleanup_release = Event(), Event()

    def worker(group, index):
        class Worker:
            def run_pure(self, inputs, params):
                nonlocal active, peak
                with condition:
                    started.append(index)
                    active += 1
                    peak = max(peak, active)
                    condition.notify_all()
                try:
                    assert release[index].wait(10)
                finally:
                    if index == first_to_finish:
                        cleaning.set()
                        assert cleanup_release.wait(10)
                    with condition:
                        active -= 1
                        finished.append(index)
                        condition.notify_all()
                return {}
        return Worker

    runtime = _python_runtime(tmp_path, [("dispatch", count, limit)], worker, execution, wrapped=wrapped)
    thread, errors = _background(runtime)
    try:
        with condition:
            assert condition.wait_for(lambda: len(started) >= capacity, timeout=5)
        release[first_to_finish].set()
        assert cleaning.wait(5)
        with condition:
            assert not condition.wait_for(lambda: capacity in started, timeout=.05)
        cleanup_release.set()
        with condition:
            assert condition.wait_for(lambda: capacity in started, timeout=5)
            assert set(started) == set(range(capacity + 1)), started
            assert finished == [first_to_finish], finished
    finally:
        cleanup_release.set()
        for event in release:
            event.set()
        thread.join(10)
    assert not thread.is_alive() and not errors, errors
    assert peak == capacity
    assert sorted(started) == sorted(finished) == list(range(count))
    assert runtime.trace.node_runs["dispatch_join"] == 1


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_python_two_dispatchers_have_independent_budgets(tmp_path, execution):
    condition, release = Condition(), Event()
    started = {"left": 0, "right": 0}

    def worker(group, index):
        class Worker:
            def run_pure(self, inputs, params):
                with condition:
                    started[group] += 1
                    condition.notify_all()
                assert release.wait(10)
                return {}
        return Worker

    runtime = _python_runtime(tmp_path, [("left", 8, 4), ("right", 8, 6)], worker, execution)
    thread, errors = _background(runtime)
    try:
        with condition:
            assert condition.wait_for(lambda: started["left"] >= 4 and started["right"] >= 6, timeout=5)
            assert started == {"left": 4, "right": 6}
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors, errors
    assert started == {"left": 8, "right": 8}


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_python_failure_does_not_start_queued_calls_and_waits_for_cleanup(tmp_path, execution):
    entered, cleaning, release_cleanup = Event(), Event(), Event()
    started = []

    def worker(group, index):
        class Worker:
            def run_pure(self, inputs, params, context):
                started.append(index)
                if index == 0:
                    assert entered.wait(5)
                    raise ValueError("dispatched call failed")
                entered.set()
                try:
                    assert context.signal.wait(5)
                finally:
                    cleaning.set()
                    assert release_cleanup.wait(10)
                return {}
        return Worker

    runtime = _python_runtime(tmp_path, [("dispatch", 8, 2)], worker, execution)
    thread, errors = _background(runtime)
    try:
        assert cleaning.wait(5)
        assert thread.is_alive() and set(started) == {0, 1}
    finally:
        release_cleanup.set()
        thread.join(10)
    assert not thread.is_alive()
    assert len(errors) == 1 and "dispatched call failed" in str(errors[0])
    assert set(started) == {0, 1}


def _javascript(tmp_path, groups, assertion, *, wrapped=False):
    nodes = [dict(id="start", definition_id="budget.start", flow_kind="terminal", is_terminal=True,
                  implementation={"kind": "file", "ref": "./nodes.mjs", "export": "empty"})]
    routes = []
    for group, count, limit in groups:
        nodes.append(dict(id=group, definition_id="budget." + group, flow_kind="process",
            max_concurrency=8 if limit is None else limit,
            implementation={"kind": "file", "ref": "./nodes.mjs", "export": "empty"}))
        routes.append(dict(source="start", target=group))
        for index in range(count):
            name = f"{group}{index}"
            call = dict(id=name, definition_id="budget." + name, flow_kind="process",
                completion="suspend", params={"group": group, "index": index},
                implementation={"kind": "file", "ref": "./nodes.mjs", "export": "worker"})
            if wrapped:
                boundary = lambda label: dict(id=label, definition_id="budget." + label, flow_kind="terminal",
                    is_terminal=True, implementation={"kind": "file", "ref": "./nodes.mjs", "export": "empty"})
                call = dict(id=name, definition_id="budget.body." + name, flow_kind="predefined", is_nodeset=True,
                    subplan=dict(nodes=[boundary("start"), dict(call, id="work"), boundary("end")],
                        routes=[dict(source="start", target="work"), dict(source="work", target="end")]))
            nodes.append(call)
            routes.extend([dict(source=group, target=name), dict(source=name, target=group + "_join")])
        nodes.append(dict(id=group + "_join", definition_id="budget." + group + "_join",
            flow_kind="process", join_policy="all",
            implementation={"kind": "file", "ref": "./nodes.mjs", "export": "empty"}))
        routes.append(dict(source=group + "_join", target="end"))
    nodes.append(dict(id="end", definition_id="budget.end", flow_kind="terminal", is_terminal=True,
        join_policy="all", implementation={"kind": "file", "ref": "./nodes.mjs", "export": "empty"}))
    emitted = emit_fixture({"entry_mode": "async", "nodes": nodes, "routes": routes})
    (tmp_path / "workflow.mjs").write_text(emitted.source)
    (tmp_path / "nodes.mjs").write_text('''
export const state = {started: [], finished: [], active: 0, peak: 0,
  release: new Map(), reject: new Map(), cleaning: [], cleanup: new Map(), holdCleanup: true};
export function empty(inputs, params) {
  if ('max_concurrency' in params) throw Error('scheduler config leaked into business parameters');
  return {};
}
export async function worker(inputs, params, context) {
  const name = params.group + params.index;
  state.started.push(name);state.active++;state.peak = Math.max(state.peak, state.active);
  const stopped = () => state.release.get(name)?.();
  try {
    await new Promise((resolve,reject) => {
      state.release.set(name, resolve);state.reject.set(name, reject);
      context.signal.addEventListener('abort', stopped, {once:true});
      if(context.signal.aborted) stopped();
    });
  } finally {
    context.signal.removeEventListener('abort', stopped);
    if(state.holdCleanup) {
      state.cleaning.push(name);
      await new Promise(resolve => state.cleanup.set(name, resolve));
    }
    state.active--;state.finished.push(name);
  }
  return {};
}
''')
    (tmp_path / "run.mjs").write_text('''
import {runWorkflowAsync} from './workflow.mjs';
import {state} from './nodes.mjs';
function check(value, message) { if(!value) throw Error(message + ': ' + JSON.stringify(state)); }
async function until(predicate) {
  const end=Date.now()+5000;
  while(!predicate()) { if(Date.now()>end) throw Error('queue stalled: '+JSON.stringify(state));await new Promise(r=>setImmediate(r)); }
}
let settled=false;
const pending=runWorkflowAsync({});
pending.finally(()=>settled=true).catch(()=>{});
''' + assertion + "\nconsole.log('PASS');\n")
    result = subprocess.run(["node", str(tmp_path / "run.mjs")], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"


@pytest.mark.parametrize("limit,count,capacity,wrapped", [(None, 12, 8, False), (4, 8, 4, False), (1, 3, 1, False), (4, 8, 4, True)])
def test_javascript_local_queue_refills_after_real_cleanup(tmp_path, limit, count, capacity, wrapped):
    _javascript(tmp_path, [("dispatch", count, limit)], f'''
await until(()=>state.started.length >= {capacity});
check(state.started.length === {capacity}, 'dispatch limit exceeded');
state.release.get('dispatch{capacity-1}')();
await until(()=>state.cleaning.includes('dispatch{capacity-1}'));
await new Promise(r=>setImmediate(r));
check(state.started.length === {capacity}, 'refilled before actual cleanup');
state.cleanup.get('dispatch{capacity-1}')();
await until(()=>state.started.includes('dispatch{capacity}'));
check(state.finished.length===1 && state.started.length==={capacity+1}, 'did not refill one free slot');
check(state.finished[0]==='dispatch{capacity-1}', 'waited for submission order instead of completion');
state.holdCleanup=false;
for(let index=0;index<{count};index++) {{
  await until(()=>state.release.has('dispatch'+index));state.release.get('dispatch'+index)();
}}
await pending;
check(state.finished.length==={count} && state.peak==={capacity}, 'lost work or exceeded capacity');
''', wrapped=wrapped)


def test_javascript_two_dispatchers_have_independent_budgets(tmp_path):
    _javascript(tmp_path, [("left", 8, 4), ("right", 8, 6)], '''
await until(()=>state.started.length >= 10);
check(state.started.filter(x=>x.startsWith('left')).length===4, 'wrong left capacity');
check(state.started.filter(x=>x.startsWith('right')).length===6, 'wrong right capacity');
state.holdCleanup=false;
for(let index=0;index<8;index++) {
 for(const group of ['left','right']) {await until(()=>state.release.has(group+index));state.release.get(group+index)();}
}
await pending;
check(state.finished.length===16 && state.peak===10, 'dispatches shared a global budget');
''')


def test_javascript_failure_cancels_running_calls_and_discards_queue(tmp_path):
    _javascript(tmp_path, [("dispatch", 8, 2)], '''
await until(()=>state.started.length===2);
state.reject.get('dispatch0')(Error('dispatched call failed'));
await until(()=>state.cleaning.includes('dispatch0'));
state.cleanup.get('dispatch0')();
await until(()=>state.cleaning.includes('dispatch1'));
check(!settled && state.started.length===2, 'root abandoned cleanup or started queued work');
state.cleanup.get('dispatch1')();
let failure;try {await pending;} catch(error) {failure=error;}
check(failure && state.started.length===2 && state.finished.length===2, 'failure did not own real cleanup');
''')
