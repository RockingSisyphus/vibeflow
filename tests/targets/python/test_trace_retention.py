from vibeflow.targets.python.runtime.trace import RuntimeTrace


def test_off_keeps_bounded_static_counts_without_iteration_paths():
    parent = RuntimeTrace(retain_details=False)
    for iteration in range(2000):
        child = RuntimeTrace(retain_details=False)
        child.record_node_run("sample", 1)
        child.record_edge("sample", "save")
        child.step_count = 2
        parent.merge_child(("monitor", f"iter_{iteration}"), child)
    assert parent.qualified_exec_order == []
    assert parent.qualified_node_runs == {}
    assert parent.qualified_edge_executions == {}
    assert parent.nested_step_count == 4000
    assert child.node_runs == {"sample": 1}
    assert child.edge_executions == {"sample->save": 1}


def test_enabled_trace_retains_iteration_details():
    parent, child = RuntimeTrace(), RuntimeTrace()
    child.record_node_run("sample", 1)
    child.record_edge("sample", "save")
    parent.merge_child(("monitor", "iter_0"), child)
    assert parent.qualified_exec_order == ["monitor.iter_0.sample"]
    assert parent.qualified_node_runs == {"monitor.iter_0.sample": 1}
    assert parent.qualified_edge_executions == {"monitor.iter_0.sample->monitor.iter_0.save": 1}
