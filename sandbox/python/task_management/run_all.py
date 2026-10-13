"""Public Python SDK/config/CLI acceptance, with artifacts outside the repository."""
from pathlib import Path
import json
import sys
import os
import signal
import subprocess
import time
sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tests.fixtures.support.addition_sandboxes import cli, events, main, workspace


def run(work, *, toolchain=None):
    workspace(FIXTURE, work)
    observations = []
    config = work / "project/configs/tasks.jsonc"
    for execution in ("plan", "compiled", "block"):
        for scenario in ("failure", "unexpected_failure", "success", "stop_return", "stop_wait", "uncooperative",
                         "selective", "invalid_refs", "cleanup_failure", "concurrent_failure", "root_failure", "unobserved_failure", "external_cancel", "workflow_join"):
            input_file = work / "input.json"
            input_file.write_text(json.dumps({"scenario": "stop_return" if scenario=="workflow_join" else scenario}))
            selected_config=config.with_name("launch_only.jsonc") if scenario in ("unobserved_failure","workflow_join") else config
            arguments=["run", "--workspace", work / "vibeflow_config.jsonc",
                "--config", selected_config, "--input", input_file, "--execution", execution,
                "--run-root", work / "runs", "--run-id", execution + "-" + scenario]
            run_dir=work/"runs"/(execution+"-"+scenario)
            expected_failure=scenario in ("root_failure","unobserved_failure","external_cancel")
            if expected_failure:
                command=[sys.executable,"-B","-m","vibeflow",*map(str,arguments)]
                environment={**os.environ,"PYTHONPATH":str(ROOT/"src"),"PYTHONDONTWRITEBYTECODE":"1"}
                process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
                if scenario=="external_cancel":
                    deadline=time.monotonic()+20
                    trace_file=run_dir/"runtime_trace.jsonl"
                    while process.poll() is None and time.monotonic()<deadline:
                        lines=trace_file.read_text().splitlines() if trace_file.exists() else []
                        records=[]
                        for line in lines:
                            try:records.append(json.loads(line))
                            except json.JSONDecodeError:pass
                        if sum(event["kind"]=="worker_started" for event in records)==3:
                            process.send_signal(signal.SIGINT)
                            break
                        time.sleep(.005)
                    else:
                        process.kill()
                        raise AssertionError("workers did not enter before cancellation")
                stdout,stderr=process.communicate(timeout=20)
                assert process.returncode != 0,stdout
                (work/(execution+"-"+scenario+"-stderr.txt")).write_bytes(stderr)
                result={"status":"expected_failure"}
            else:
                result=json.loads(cli(arguments).stdout)
                assert result["status"] in {"PASS", "CONCERNS"}, result
            trace = events(run_dir / "runtime_trace.jsonl")
            first = next((event for event in trace if event["kind"] == "first_outcome"), None)
            if scenario in ("failure", "unexpected_failure", "cleanup_failure"):
                outcome = first["details"]["outcome"]
                assert outcome["status"] == "failed" and outcome["task"]["task_id"] == "2", outcome
                assert outcome["error"]["source_location"], outcome
                notified = trace.index(first)
                assert any(event["kind"] == "cleanup_finished" and event["details"]["label"] == "B"
                           for event in trace[:notified]), trace
            joined = next((index for index, event in enumerate(trace) if event["kind"] == "control_joined"),len(trace))
            # Queued tasks stopped before execution need no cleanup; every task that
            # did start must complete its finally before the join.
            started = {event["details"]["label"] for event in trace if event["kind"] == "worker_started"}
            cleaned = {event["details"]["label"] for event in trace[:joined] if event["kind"] == "cleanup_finished"}
            assert started == cleaned, trace
            status = json.loads((run_dir / "status.json").read_text())
            assert status["state"] == ("failed" if expected_failure else "succeeded"), status
            if scenario=="unobserved_failure":assert "VF_TASK_UNOBSERVED" in status["error"],status
            if scenario=="root_failure":assert "parent failed" in status["error"],status
            if scenario=="invalid_refs":assert sum(event["kind"]=="expected_contract_error" for event in trace)==3,trace
            if scenario=="cleanup_failure":assert "cleanup failed" in json.dumps(first) and "failed deliberately" in json.dumps(first),first
            assert (run_dir / "graph.svg").is_file(), list(run_dir.iterdir())
            observations.append({"execution":execution,"scenario":scenario,"status":"PASS",
                                 "framework_status":result["status"],"started":sorted(started),"cleaned":sorted(cleaned)})
    project_options=work/"project/vibeflow_project.jsonc"
    options=json.loads(project_options.read_text())
    options["runtime"]={"async_max_workers":1}
    project_options.write_text(json.dumps(options))
    for execution in ("plan","compiled","block"):
        for nested in ("nested","nested_manager"):
            for scenario in ("success","stop_wait"):
                input_file.write_text(json.dumps({"scenario":scenario}))
                run_id=f"{execution}-{nested}-{scenario}"
                result=json.loads(cli(["run","--workspace",work/"vibeflow_config.jsonc","--config",config.with_name(nested+".jsonc"),
                    "--input",input_file,"--execution",execution,"--run-root",work/"runs","--run-id",run_id]).stdout)
                assert result["status"] in {"PASS","CONCERNS"},result
                trace=events(work/"runs"/run_id/"runtime_trace.jsonl")
                started={event["details"]["label"] for event in trace if event["kind"]=="worker_started"}
                cleaned={event["details"]["label"] for event in trace if event["kind"]=="cleanup_finished"}
                assert started==cleaned,trace
                assert sum(event["kind"]=="task_exited" for event in trace)==(4 if nested=="nested_manager" else 3),trace
                if nested=="nested_manager":assert any(event["kind"]=="nested_joined" for event in trace),trace
                observations.append({"execution":execution,"config":nested,"scenario":scenario,"workers":1,"status":"PASS"})
    return {"status":"PASS", "observations":observations}


if __name__ == "__main__":
    main(run, "Python task management")
