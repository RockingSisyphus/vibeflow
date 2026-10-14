"""Actual task execution outlives cancellation of its caller's wait."""
from threading import Event, Thread
import time

import pytest

from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.project.graph_config import parse_graph_config


class Terminal:
    def run_pure(self, inputs, params):
        return {}


@pytest.mark.parametrize("execution", ("plan", "compiled", "block"))
def test_failed_task_notifies_after_finally_and_stop_waits_for_execution(tmp_path, execution):
    cleaned, started = Event(), Event()
    order = []

    class Worker:
        def run_pure(self, inputs, params, context):
            started.set()
            try:
                context.signal.wait()
            finally:
                order.append("cleanup_start")
                time.sleep(.04)
                cleaned.set()
                order.append("cleanup_done")
            return {}

    class Failure:
        def run_pure(self, inputs, params, context):
            started.wait()
            try:
                raise ValueError("B failed")
            finally:
                order.append("B_cleaned")

    class Manager:
        def run_pure(self, inputs, params, context):
            refs = [context.tasks.start("A", {}), context.tasks.start("B", {})]
            first = context.tasks.wait_any(refs)
            assert first["task"] == refs[1]
            assert first["status"] == "failed"
            assert "B failed" in first["error"]["message"]
            assert order == ["B_cleaned"]
            pending = [ref for ref in refs if ref != first["task"]]
            context.tasks.request_stop(pending)
            results = [*context.tasks.wait_all_exited([*pending, pending[0]]), first]
            assert [item["status"] for item in results] == ["cancelled", "failed"]
            assert cleaned.is_set()
            assert context.tasks.wait_any([]) is None
            assert context.tasks.wait_all_exited([]) == []
            with pytest.raises(Exception, match="VF_TASK_REF_INVALID"):
                context.tasks.wait_any([refs[1]])
            return {}

    registry = native_registry()
    for key, kind, implementation in (("terminal", "terminal", Terminal), ("manager", "task_manager", Manager),
                                      ("worker", "process", Worker), ("failure", "process", Failure)):
        registry.register(NodeDescriptor("test."+key, key, "Task fixture", "1", kind,
            contract=NodeContractDescriptor(), rulesets=()), implementation)
    graph = parse_graph_config({"pipeline": {"nodes": [
        {"id": "start", "type_used": "test.terminal", "display_name": "start", "description": "Start"},
        {"id": "manage", "type_used": "test.manager", "display_name": "manage", "description": "Manage tasks",
         "task_targets": {"A": {"type_used": "test.worker"}, "B": {"type_used": "test.failure"}}},
        {"id": "end", "type_used": "test.terminal", "display_name": "end", "description": "End"}],
        "edges": [{"from": "start", "to": "manage"}, {"from": "manage", "to": "end"}], "outputs": []}})
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
                              runtime_options=RuntimeOptions(execution=execution))
    runtime.run({})
    assert order == ["B_cleaned", "cleanup_start", "cleanup_done"]
    assert all(task.signal is None for task in runtime._tasks._records.values())


def make_runtime(tmp_path, manager, targets, *, workers=4, execution="plan"):
    """Use the real native registry/config, rather than mock executor records."""
    registry = native_registry()
    for key, kind, implementation in (("terminal", "terminal", Terminal),
                                      ("manager", "task_manager", manager), *targets):
        registry.register(NodeDescriptor("test."+key, key, "Task fixture", "1", kind,
            contract=NodeContractDescriptor(), rulesets=()), implementation)
    graph = parse_graph_config({"pipeline": {"nodes": [
        {"id": "start", "type_used": "test.terminal", "display_name": "start", "description": "Start"},
        {"id": "manage", "type_used": "test.manager", "display_name": "manage", "description": "Manage tasks",
         "task_targets": {key: {"type_used": "test."+key} for key, _, _ in targets}},
        {"id": "end", "type_used": "test.terminal", "display_name": "end", "description": "End"}],
        "edges": [{"from": "start", "to": "manage"}, {"from": "manage", "to": "end"}], "outputs": []}})
    return PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
        runtime_options=RuntimeOptions(execution=execution, async_max_workers=workers))


def background_run(runtime):
    finished, errors = Event(), []
    def run():
        try:
            runtime.run({})
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()
    thread = Thread(target=run)
    thread.start()
    return thread, finished, errors


def test_stop_without_wait_returns_node_but_workflow_waits(tmp_path):
    started, cleaning, release, node_returned = (Event() for _ in range(4))
    class Worker:
        def run_pure(self, inputs, params, context):
            started.set()
            try:
                context.signal.wait()
            finally:
                cleaning.set()
                release.wait()
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            ref = context.tasks.start("worker", {})
            assert started.wait(2)
            ack = context.tasks.request_stop([ref])
            assert ack[0]["state"] == "stop_requested"
            node_returned.set()
            return {}
    runtime = make_runtime(tmp_path, Manager, (("worker", "process", Worker),))
    thread, finished, errors = background_run(runtime)
    try:
        assert node_returned.wait(2) and cleaning.wait(2)
        assert not finished.is_set()
    finally:
        release.set()
        thread.join(2)
    assert finished.is_set() and errors == []


def test_external_cancel_keeps_uncooperative_operation_and_finally_owned(tmp_path):
    started, underlying_release, cleaning, cleanup_release = (Event() for _ in range(4))
    class Worker:
        def run_pure(self, inputs, params, context):
            started.set()
            try:
                underlying_release.wait()  # Deliberately ignores cancellation.
            finally:
                cleaning.set()
                cleanup_release.wait()
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            context.tasks.wait_any([context.tasks.start("worker", {})])
            return {}
    runtime = make_runtime(tmp_path, Manager, (("worker", "process", Worker),))
    thread, finished, errors = background_run(runtime)
    try:
        assert started.wait(2)
        runtime.request_stop()
        assert not finished.is_set() and not cleaning.is_set()
        underlying_release.set()
        assert cleaning.wait(2) and not finished.is_set()
    finally:
        underlying_release.set()
        cleanup_release.set()
        thread.join(2)
    assert finished.is_set() and len(errors) == 1
    assert "VF_ABORTED" in str(errors[0])
    assert all(task.signal is None for task in runtime._tasks._records.values())


def test_queued_stop_and_pool_saturation(tmp_path):
    started, ran_queued = Event(), Event()
    class Slow:
        def run_pure(self, inputs, params, context):
            started.set()
            context.signal.wait()
            return {}
    class Queued:
        def run_pure(self, inputs, params, context):
            ran_queued.set()
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            first = context.tasks.start("slow", {})
            assert started.wait(2)
            second = context.tasks.start("queued", {})
            context.tasks.request_stop([second])
            context.tasks.request_stop([first])
            outcomes = context.tasks.wait_all_exited([first, second])
            assert [item["status"] for item in outcomes] == ["cancelled", "cancelled"]
            assert not ran_queued.is_set()
            return {}
    runtime = make_runtime(tmp_path, Manager, (("slow", "process", Slow), ("queued", "process", Queued)), workers=1)
    thread, finished, errors = background_run(runtime)
    thread.join(2)
    if not finished.is_set():
        runtime.request_stop()
        thread.join(2)
    assert finished.is_set() and errors == []


def test_unconsumed_failure_is_not_swallowed(tmp_path):
    failed = Event()
    class Failure:
        def run_pure(self, inputs, params, context):
            try:
                raise ValueError("unobserved B")
            finally:
                failed.set()
    class Manager:
        def run_pure(self, inputs, params, context):
            context.tasks.start("failure", {})
            assert failed.wait(2)
            return {}
    runtime = make_runtime(tmp_path, Manager, (("failure", "process", Failure),))
    with pytest.raises(Exception, match="VF_TASK_UNOBSERVED.*unobserved B"):
        runtime.run({})


def test_validation_late_results_and_foreign_run_reference(tmp_path):
    refs = []
    class Worker:
        def run_pure(self, inputs, params, context):
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            if refs:
                with pytest.raises(Exception, match="VF_TASK_REF_INVALID"):
                    context.tasks.wait_any([refs[0]])
            ref = context.tasks.start("worker", {})
            refs.append(ref)
            outcomes = context.tasks.wait_all_exited([ref, ref])
            assert len(outcomes) == 1 and outcomes[0]["status"] == "succeeded"
            with pytest.raises(Exception, match="VF_TASK_TARGET_UNKNOWN"):
                context.tasks.start("not-declared", {})
            with pytest.raises(Exception, match="VF_TASK_REF_INVALID"):
                context.tasks.wait_any([{"run_id": ref["run_id"], "task_id": "missing"}])
            return {}
    runtime = make_runtime(tmp_path, Manager, (("worker", "process", Worker),))
    runtime.run({})
    runtime.run({})
    assert refs[0]["run_id"] != refs[1]["run_id"]


def test_ordinary_node_has_no_controller_with_rules_disabled(tmp_path):
    class Ordinary:
        def run_pure(self, inputs, params, context):
            with pytest.raises(Exception, match="VF_TASK_CONTROL_FORBIDDEN"):
                context.tasks.request_stop([])
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            outcome = context.tasks.wait_any([context.tasks.start("ordinary", {})])
            assert outcome["status"] == "succeeded"
            return {}
    runtime = make_runtime(tmp_path, Manager, (("ordinary", "process", Ordinary),))
    runtime.run({})


@pytest.mark.parametrize('nested',[False,True])
def test_task_target_all_inputs_preserve_envelopes(tmp_path,nested):
    from vibeflow.core.contracts import DataProvider,DataRequirement
    class Sum:
        def run_pure(self,inputs,params):
            return {'sum':sum(item['value'] for item in inputs['number'])}
    class Manager:
        def run_pure(self,inputs,params,context):
            refs=[context.tasks.start('sum',{'number':numbers}) for numbers in ([],[1],[1,2,3])]
            outcomes=context.tasks.wait_all_exited(refs)
            assert [item['outputs']['sum'] for item in outcomes]==[0,1,6]
            return {}
    runtime=make_runtime(tmp_path,Manager,())
    runtime.registry.register(NodeDescriptor('test.sum','Sum','Many input envelopes','1','process',
        contract=NodeContractDescriptor(requires=(DataRequirement('number','all',display_name='Numbers'),),provides=(DataProvider('sum','sum',display_name='Sum'),),input_semantics={'number':('All supplied numbers',)},output_semantics={'sum':('Total',)}),rulesets=()),Sum)
    from dataclasses import replace
    from vibeflow.core.flow import NodeSpec
    graph=replace(runtime.graph,nodes=tuple(replace(node,task_targets={'sum':NodeSpec('sum','test.sum')}) if node.id=='manage' else node for node in runtime.graph.nodes))
    if nested:
        definition=parse_graph_config({'nodesets':[{'type_key':'test.sum_block','display_name':'Sum block','description':'Preserve all envelopes',
            'requires':[{'type':'number','cardinality':'all','display_name':'Numbers'}],
            'provides':[{'key':'sum','type':'sum','display_name':'Sum'}],
            'pipeline':{'inputs':[{'key':'numbers','type':'number','required':False,'display_name':'Numbers'}],
                'nodes':[{'id':'start','type_used':'test.terminal','display_name':'Start','description':'Enter block'},
                    {'id':'sum','type_used':'test.sum','display_name':'Sum','description':'Sum all inputs'},
                    {'id':'end','type_used':'test.terminal','display_name':'End','description':'Exit block'}],
                'edges':[{'from':'start','to':'sum'},{'from':'sum','to':'end'}],
                'outputs':[{'type':'sum','cardinality':'exactly_one','as':'sum','display_name':'Sum'}]}}],
            'pipeline':{'nodes':[{'id':'start','type_used':'test.terminal','display_name':'Start','description':'Parse definition'}]}}).nodesets
        graph=replace(graph,nodesets=definition,nodes=tuple(replace(node,task_targets={'sum':NodeSpec('sum','test.sum_block')}) if node.id=='manage' else node for node in graph.nodes))
    PipelineRuntime(graph,registry=runtime.registry,run_dir=tmp_path/'actual').run({})


def test_many_short_tasks_transfer_results_and_reclaim_records(tmp_path):
    class Worker:
        def run_pure(self, inputs, params):
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            refs, held = [], []
            for batch in range(16):
                current = [context.tasks.start('worker', {}) for _ in range(64)]
                outcomes = context.tasks.wait_all_exited([*current, current[0]])
                assert len(outcomes) == 64 and all(item['status']=='succeeded' for item in outcomes)
                held.extend(outcomes)
                refs.extend(current)
                assert not context._runtime._tasks._records
            assert len({ref['task_id'] for ref in refs}) == 1024
            assert len(held) == 1024 and held[0]['status']=='succeeded'
            with pytest.raises(Exception, match="VF_TASK_REF_INVALID"):
                context.tasks.wait_any([dict(refs[0])])
            return {}
    runtime = make_runtime(tmp_path, Manager, (('worker','process',Worker),))
    runtime.run({})
    assert not runtime._tasks._records
    assert not runtime._tasks._controls and not runtime._tasks._pools


def test_completed_before_receiving_result_is_consumed_only_once(tmp_path):
    entered, release = Event(), Event()
    class Worker:
        def run_pure(self, inputs, params):
            entered.set()
            release.wait()
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            ref = context.tasks.start('worker', {})
            entered.wait()
            release.set()
            registry = context._runtime._tasks
            with registry._condition:
                registry._condition.wait_for(lambda: registry._records[ref['task_id']].outcome is not None)
            assert context.tasks.request_stop([ref])[0]['state'] == 'already_exited'
            result = context.tasks.wait_any([ref])
            assert result['status'] == 'succeeded' and not registry._records
            with pytest.raises(Exception, match='VF_TASK_REF_INVALID'):
                context.tasks.wait_all_exited([dict(ref)])
            assert result['status'] == 'succeeded'
            return {}
    make_runtime(tmp_path, Manager, (('worker','process',Worker),)).run({})


def test_overlapping_waiters_cannot_deliver_the_same_result_twice(tmp_path):
    release, selected = Event(), Event()
    results, selection_count = [], []
    class Worker:
        def run_pure(self, inputs, params):
            release.wait()
            return {}
    class Manager:
        def run_pure(self, inputs, params, context):
            ref = context.tasks.start('worker', {})
            registry = context._runtime._tasks
            original = registry.select
            def select(refs):
                tasks = original(refs)
                with registry._condition:
                    selection_count.append(1)
                    if len(selection_count) == 2:
                        selected.set()
                return tasks
            registry.select = select
            def receive():
                try:
                    results.append(context.tasks.wait_any([ref])['status'])
                except Exception as error:
                    results.append(error.code)
            threads = [Thread(target=receive) for _ in range(2)]
            for thread in threads: thread.start()
            assert selected.wait(2)
            release.set()
            for thread in threads: thread.join(2)
            assert sorted(results) == ['VF_TASK_REF_INVALID', 'succeeded']
            assert not registry._records
            return {}
    make_runtime(tmp_path, Manager, (('worker','process',Worker),)).run({})


def test_parent_failure_keeps_cleanup_and_failure_hook_errors(tmp_path):
    from vibeflow.targets.python.project import PluginRegistry
    from vibeflow.targets.python.runtime.options import runtime_hook_plan
    started=Event()
    class Worker:
        def run_pure(self,inputs,params,context):
            started.set()
            try:context.signal.wait()
            finally:raise RuntimeError('worker cleanup failed')
    class Manager:
        def run_pure(self,inputs,params,context):
            context.tasks.start('worker',{})
            assert started.wait(2)
            raise ValueError('parent primary failure')
    class Hook:
        def run_failed(self,result,trace,failure):
            raise RuntimeError('failure hook also failed')
    runtime=make_runtime(tmp_path,Manager,(('worker','process',Worker),))
    plugins=PluginRegistry();plugins.register(Hook(),plugin_type='runtime',name='cleanup-hook')
    runtime._hook_plan=runtime_hook_plan(plugins.runtime_plugins(),runtime.runtime_options)
    with pytest.raises(ValueError,match='parent primary failure') as caught:runtime.run({})
    errors=caught.value.cleanup_errors
    assert len(errors)==2
    assert 'worker cleanup failed' in str(errors[0])
    assert 'failure hook also failed' in str(errors[1])
    assert 'parent primary failure' in runtime.trace.exception
    assert all(task.signal is None for task in runtime._tasks._records.values())


@pytest.mark.parametrize('manager_target',[False,True])
def test_executor_startup_failure_does_not_leave_a_live_task(tmp_path,monkeypatch,manager_target):
    import vibeflow.targets.python.runtime.tasks as tasks
    class Worker:
        def run_pure(self,inputs,params,context):
            raise AssertionError('failed startup must not enter business code')
    class Manager:
        def run_pure(self,inputs,params,context):
            context.tasks.start('worker',{})
            return {}
    runtime=make_runtime(tmp_path,Manager,(('worker','task_manager' if manager_target else 'process',Worker),))
    original=tasks.Thread.start
    def fail_start(thread):
        if thread.name.startswith('vibeflow-task'):
            raise RuntimeError('executor thread startup failed')
        return original(thread)
    monkeypatch.setattr(tasks.Thread,'start',fail_start)
    with pytest.raises(RuntimeError,match='executor thread startup failed'):runtime.run({})
    assert all(task.phase=='exited' and task.signal is None for task in runtime._tasks._records.values())
    assert not runtime._tasks._controls and not runtime._tasks._pools
