"""Graph scheduler cancellation owns real Node execution through final cleanup."""
from threading import Event,Thread
import time
import pytest
from tests.conformance.test_graph_concurrency import _call
from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeDescriptor,NodeContractDescriptor
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.targets.python.runtime import PipelineRuntime,RuntimeOptions


def _runtime(tmp_path, implementations, execution="plan", plugin_registry=None, lock=""):
    registry=native_registry()
    class Terminal:
        def run_pure(self,inputs,params):return {}
    registry.register(NodeDescriptor("native.terminal","Boundary","Boundary","1","terminal",contract=NodeContractDescriptor(),rulesets=(), node_type="vibeflow.node"),Terminal)
    for name,impl in implementations.items():
        registry.register(NodeDescriptor("native."+name,name,name,"1","process",contract=NodeContractDescriptor(),rulesets=(), node_type="vibeflow.node"),impl)
    graph=parse_graph_config({"pipeline":{"nodes":[_call("start","native.terminal"),
        *[_call(name,"native."+name,**({"execution_lock":{"key":lock}} if lock else {})) for name in implementations],_call("end","native.terminal",join_policy="all")],
        "edges":[["start",name] for name in implementations]+[[name,"end"] for name in implementations]}})
    return PipelineRuntime(graph,registry=registry,run_dir=tmp_path,plugin_registry=plugin_registry,runtime_options=RuntimeOptions(execution=execution))


@pytest.mark.parametrize("execution",["plan","block","compiled"])
def test_external_cancel_waits_for_uncooperative_work_and_finally(tmp_path,execution):
    entered,release,cleaned=Event(),Event(),Event()
    class Worker:
        def run_pure(self,inputs,params,context):
            entered.set()
            try:assert release.wait(3)
            finally:
                time.sleep(.02);cleaned.set()
            return {}
    runtime=_runtime(tmp_path,{"worker":Worker},execution)
    errors=[]
    def run():
        try:runtime.run()
        except BaseException as error:errors.append(error)
    running=Thread(target=run);running.start()
    try:
        assert entered.wait(2)
        runtime.request_stop("cancel")
        assert running.is_alive() and not cleaned.is_set()
    finally:release.set();running.join(3)
    assert not running.is_alive() and cleaned.is_set()
    assert errors and getattr(errors[0],"code","")=="VF_ABORTED"


def test_node_has_no_task_controller_even_with_rules_disabled(tmp_path):
    class Worker:
        def run_pure(self,inputs,params,context):
            assert not hasattr(context,"tasks")
            return {}
    _runtime(tmp_path,{"worker":Worker}).run()


def test_thread_start_failure_cleans_already_started_sibling(tmp_path,monkeypatch):
    entered,cleaned=Event(),Event()
    class Worker:
        def run_pure(self,inputs,params,context):
            entered.set()
            try:context.signal.wait(2)
            finally:cleaned.set()
            return {}
    runtime=_runtime(tmp_path,{"first":Worker,"second":Worker})
    original=Thread.start
    def start(thread):
        if thread.name=="vibeflow-node:second":
            assert entered.wait(2)
            raise RuntimeError("thread launch failed")
        return original(thread)
    monkeypatch.setattr(Thread,"start",start)
    with pytest.raises(RuntimeError,match="thread launch failed"):runtime.run()
    assert cleaned.is_set()


@pytest.mark.parametrize("execution",["block","compiled"])
def test_block_failure_observer_preserves_primary_and_reports_cleanup(tmp_path,execution):
    from vibeflow.targets.python.project.plugins import PluginRegistry
    observed=[]
    class Worker:
        def run_pure(self,inputs,params):raise ValueError("original branch failure")
    class Hooks:
        def block_failed(self,name,nodes,error):
            observed.append((name,nodes,error))
            raise RuntimeError("block observer failure")
    plugins=PluginRegistry();plugins.register(Hooks(),plugin_type="runtime",name="observer")
    runtime=_runtime(tmp_path,{"worker":Worker},execution,plugins)
    with pytest.raises(ValueError,match="original branch failure") as caught:runtime.run()
    assert len(observed)==1 and "original branch failure" in observed[0][2]
    assert any("block observer failure" in str(error) for error in caught.value.cleanup_errors)



def test_parallel_trace_events_and_edge_counts_are_not_lost():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from vibeflow.targets.python.runtime.trace import RuntimeTrace
    trace=RuntimeTrace();barrier=Barrier(8)
    def record():
        barrier.wait(timeout=2)
        for _ in range(1000):
            trace.record_edge("source","sink")
            trace.add_event({"kind":"probe"},("worker",))
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(lambda _:record(),range(8)))
    summary=trace.to_dict()
    assert summary["event_count"]==8000
    assert summary["edge_executions"]=={"source->sink":8000}



def test_cancelled_invocation_waiting_for_a_lock_never_enters_business_code(tmp_path):
    import json
    from concurrent.futures import ThreadPoolExecutor
    entered,release=Event(),Event();executed=[]
    class Holder:
        def run_pure(self,inputs,params):
            entered.set();assert release.wait(10);return {}
    class Waiting:
        def run_pure(self,inputs,params):executed.append("unexpected");return {}
    holder=_runtime(tmp_path/"holder",{"holder":Holder},lock="native.cancelled-waiter")
    waiting=_runtime(tmp_path/"waiting",{"first":Waiting,"second":Waiting},lock="native.cancelled-waiter")
    with ThreadPoolExecutor(max_workers=2) as roots:
        held=roots.submit(holder.run);assert entered.wait(3)
        blocked=roots.submit(waiting.run)
        try:
            trace=tmp_path/"waiting/runtime_trace.jsonl";deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                events=[]
                if trace.exists():
                    for line in trace.read_text().splitlines():
                        try:events.append(json.loads(line))
                        except json.JSONDecodeError:pass
                if sum(item["kind"]=="lock_wait" for item in events)>=2:break
                time.sleep(.01)
            else:raise AssertionError("independent invocations never reached lock wait")
            waiting.request_stop("cancel while waiting");release.set()
            with pytest.raises(Exception,match="VF_ABORTED"):blocked.result(timeout=5)
            held.result(timeout=5)
        finally:
            waiting.request_stop("test cleanup");release.set()
    assert executed==[]
