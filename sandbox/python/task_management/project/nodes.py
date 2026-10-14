"""Node-owned waits and cleanup, controlled through SDK task references."""
import time
from vibeflow.targets.python.sdk import NodeRunContext


class Terminal:
    def run_pure(self, inputs, params):
        return {}


class Launch:
    def run_pure(self, inputs, params, context: NodeRunContext):
        scenario = inputs["fixture.scenario"]["value"]
        refs = [context.tasks.start("worker", {"fixture.request": {"label": label, "scenario": scenario}})
                for label in ("A", "B", "C")]
        finished = []
        if scenario == "selective":
            extra = context.tasks.start("worker", {"fixture.request": {"label": "D", "scenario": "success"}})
            assert len({ref["task_id"] for ref in [*refs, extra]}) == 4
            context.tasks.request_stop([refs[1]])
            finished.extend(context.tasks.wait_all_exited([refs[1]]))
            refs.pop(1)
            assert context.tasks.wait_any([extra])["status"] == "succeeded"
            context.tasks.request_stop(refs)
        elif scenario == "invalid_refs":
            for operation in (lambda: context.tasks.start("undeclared", {}),
                              lambda: context.tasks.wait_any([{"run_id": "foreign", "task_id": "1"}]),
                              lambda: context.tasks.wait_any([{"run_id": refs[0]["run_id"], "task_id": "unknown"}])):
                try:
                    operation()
                except Exception as error:
                    context.trace("expected_contract_error", {"error": str(error)})
                else:
                    raise AssertionError("invalid operation accepted")
            context.tasks.request_stop(refs)
        elif scenario in ("root_failure", "unobserved_failure"):
            finished.extend(context.tasks.wait_all_exited([refs.pop(0)]))
            if scenario == "root_failure":
                raise ValueError("parent failed after starting B and C")
        if scenario in ("failure", "unexpected_failure", "cleanup_failure"):
            first = context.tasks.wait_any(refs)
            context.trace("first_outcome", {"outcome": first})
            finished.append(first)
            refs = [ref for ref in refs if ref != first["task"]]
            context.tasks.request_stop(refs)
        elif scenario in ("stop_return", "stop_wait", "uncooperative"):
            context.tasks.request_stop(refs)
            if scenario == "stop_wait":
                finished.extend(context.tasks.wait_all_exited(refs))
                refs = []
        context.trace("manager_return", {"scenario": scenario})
        return {"fixture.refs": refs, "fixture.finished": finished}


class Relay:
    def run_pure(self, inputs, params):
        original = inputs["fixture.refs"]["value"]
        copied = list(original)
        return {"fixture.forwarded": copied,
                "fixture.finished.forwarded": inputs["fixture.finished"]["value"]}


class Control:
    def run_pure(self, inputs, params, context: NodeRunContext):
        refs = inputs["fixture.forwarded"]["value"]
        outcomes = [*inputs["fixture.finished.forwarded"]["value"],
                    *context.tasks.wait_all_exited([*refs, *refs[:1]])]
        outcomes.sort(key=lambda item: int(item["task"]["task_id"]))
        assert context.tasks.wait_any([]) is None
        assert context.tasks.wait_all_exited([]) == []
        if refs:
            try:
                context.tasks.wait_any(refs)
            except Exception as error:
                assert "VF_TASK_REF_INVALID" in str(error)
            else:
                raise AssertionError("consumed result remained available")
        context.trace("control_joined")
        return {"fixture.report": outcomes}


class Worker:
    def run_pure(self, inputs, params, context: NodeRunContext):
        request = inputs["fixture.request"]["value"]
        label, scenario = request["label"], request["scenario"]
        context.trace("worker_started", {"label": label})
        try:
            if scenario in ("failure", "cleanup_failure", "concurrent_failure", "unobserved_failure") and (label == "B" or scenario in ("concurrent_failure", "unobserved_failure")):
                raise ValueError("B failed deliberately")
            if scenario == "unexpected_failure" and label == "B":
                request["missing"]
            if scenario == "uncooperative":
                time.sleep(.04)
                context.trace("underlying_finished", {"label":label})
                return {"fixture.value":label}
            if scenario in ("success", "root_failure") and label == "A" or scenario == "success":
                return {"fixture.value": label}
            context.signal.wait()
            return {"fixture.value": label}
        finally:
            context.trace("cleanup_started", {"label": label})
            time.sleep(.08 if scenario == "unobserved_failure" and label == "A" else .04)
            context.trace("cleanup_finished", {"label": label})
            if scenario == "cleanup_failure" and label == "B":
                raise RuntimeError("B cleanup failed")


class Nested:
    def run_pure(self, inputs, params, context: NodeRunContext):
        ref=context.tasks.start("nested", {"fixture.scenario":inputs["fixture.scenario"]["value"]})
        outcome=context.tasks.wait_any([ref])
        if outcome["status"] != "succeeded":
            raise RuntimeError(str(outcome["error"]))
        context.trace("nested_joined")
        return {"fixture.report":outcome["outputs"]["fixture.report"]}
