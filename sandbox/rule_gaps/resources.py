"""Multi-file resource acceptance: real CLI checks, execution and final SVG."""
import os
import importlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def run_cases(work_root:Path,variant="current",toolchain_root=None):
    if variant!="current":raise ValueError("resource cases require the current implementation")
    groups=("registration","ownership","rules","edits","display","runtime")
    selected=os.environ.get("VIBEFLOW_RESOURCE_CASE_GROUP")
    rows=[]
    if selected:
        if selected not in groups:raise ValueError("unknown resource group: "+selected)
        name=selected
        module=importlib.import_module("resource_"+name)
        group=module.run_cases(work_root/name,toolchain_root)
        rows.extend(group);print(f"resources {name}: {len(group)} observations",flush=True)
    else:
        # Each family has its own process so SDK bootstrap modules and registry
        # binding state cannot leak between concurrent observations.
        work_root.mkdir(parents=True,exist_ok=True)
        def observe(name):
            output=work_root/(name+"-observations.json")
            command=[sys.executable,str(Path(__file__).with_name("worker.py")),"--group","resources",
                     "--work",str(work_root),"--output",str(output)]
            if toolchain_root:command.extend(("--toolchain",str(toolchain_root)))
            with (work_root/(name+"-runner.log")).open("w") as log:
                subprocess.run(command,env={**os.environ,"VIBEFLOW_RESOURCE_CASE_GROUP":name},
                               stdout=log,stderr=subprocess.STDOUT,check=True)
            return json.loads(output.read_text())
        with ThreadPoolExecutor(max_workers=2) as pool:
            for name,group in zip(groups,pool.map(observe,groups)):
                rows.extend(group);print(f"resources {name}: {len(group)} observations",flush=True)
        counts={family:sum(row["family"]==family for row in rows) for family in (
            "resource-registration","resource-ownership","resource-rules","resource-edits","resource-display","resource-runtime")}
        minima=(40,48,32,32,64,24)
        if any(actual<minimum for actual,minimum in zip(counts.values(),minima)):
            raise ValueError(f"resource matrix incomplete: {counts}")
    return rows
