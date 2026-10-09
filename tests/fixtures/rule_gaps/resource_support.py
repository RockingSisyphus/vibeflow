"""Actual SDK projects and CLI evidence for the multi-file resource matrix."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from common import ROOT, normalize, row, write

KINDS = ("node", "base_lib", "plugin", "host_extension")
FILES = {"node":"node.ts", "base_lib":"math.ts", "plugin":"plugin.ts", "host_extension":"host.ts"}
PARTS = {"node":"node_support.ts", "base_lib":"math_support.ts", "plugin":"plugin_support.ts", "host_extension":"host_support.ts"}
IDS = {"node":"demo.model", "base_lib":"demo.math", "plugin":"demo.runtime", "host_extension":"demo.host"}


def project(work, target="javascript", toolchain=None):
    destination = Path(work)
    shutil.copytree(ROOT / "sandbox" / target / "multifile_resources", destination,
        ignore=shutil.ignore_patterns("node_modules","__pycache__","ARCHITECTURE.jsonc","*.svg","*.png"))
    data = json.loads((destination / "vibeflow_project.jsonc").read_text())
    data.pop("architecture",None)
    write(destination / "vibeflow_project.jsonc",data)
    if target == "javascript":
        (destination / "node_modules").symlink_to(toolchain / "node_modules",target_is_directory=True)
    return destination


def config(project, update=None):
    path = project / "workflow.jsonc"
    value = json.loads(path.read_text())
    if update is not None:
        update(value)
        write(path,value)
    return value


def replace(project, file, old, new):
    path = project / file
    text = path.read_text()
    if old not in text:
        raise ValueError(f"fixture edit missing {old!r} in {file}")
    path.write_text(text.replace(old,new))


def cli(project, command, *, name, extra=(), config_file="workflow.jsonc", timeout=240):
    args = [sys.executable,"-m","vibeflow",command,"--workspace",str(project / "vibeflow_config.jsonc")]
    if command != "quality-check":args += ["--config",str(project / config_file)]
    if command in {"validate","quality-check","review-rules","inspect-resources"}:args.append("--json")
    args.extend(map(str,extra))
    result = subprocess.run(args,cwd=project,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"},
        capture_output=True,text=True,check=False,timeout=timeout)
    logs = project / "evidence"
    logs.mkdir(exist_ok=True)
    write(logs / (name + ".json"),{"command":args,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
    return normalize(result)


def observe(case_id, family, actual, *, accept=True, code=None, metrics=None, title=None):
    expected = {"should_accept":accept,"metrics":{"exit_code":0 if accept else 1,"json_output":True,**(metrics or {})}}
    if code:
        expected.update(codes=[{"code":code,"severity":"error"}])
        if not code.startswith(("PLUGIN.","RESOURCE.SOURCE.")):
            expected["located_codes"]=[code]
    return row("resources." + case_id,title or case_id,family,actual,expected)


def declarations(actual):
    return [item["descriptor"] for item in actual["payload"].get("resources", ())]


def mutate_presentation(project, kind, fields):
    file = FILES[kind]
    path = project / file
    text = path.read_text()
    marker = "presentation:"
    start = text.index(marker) + len(marker)
    end = text.index("}",start)+1
    text = text[:start] + json.dumps(fields,ensure_ascii=False) + text[end:]
    path.write_text(text)


def register_architecture(project):
    path = project / "vibeflow_project.jsonc"
    data = json.loads(path.read_text())
    data["architecture"] = {"documents":[{"workflow":"workflow.jsonc","document":"ARCHITECTURE.jsonc"}]}
    write(path,data)


def documents(project, *, name="diagram", screenshot=False):
    register_architecture(project)
    svg = project / "evidence" / (name + ".svg")
    svg.parent.mkdir(exist_ok=True)
    actual = cli(project,"review",name=name,extra=["--output",svg])
    document = project / "ARCHITECTURE.jsonc"
    payload = {}
    if document.exists():
        text = document.read_text();payload=json.loads(text[text.index("{"):])
    mermaid_path = project / "evidence" / (name + ".mmd")
    exported = cli(project, "export-mermaid", name=name + "-mermaid",
                   extra=["--mermaid-layout", "review-columns", "--output", mermaid_path])
    actual["metrics"]["mermaid_exit_code"] = exported["metrics"]["exit_code"]
    mermaid = mermaid_path.read_text() if mermaid_path.exists() else ""
    browser = {"nodes":[]}
    if svg.exists():
        renderer=os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT","")
        args=["node",str(ROOT / "tests/fixtures/rule_gaps/resource_browser.mjs"),renderer,str(svg)]
        if screenshot:args.append(str(project / "evidence" / (name + ".png")))
        process=subprocess.run(args,capture_output=True,text=True,check=False,timeout=120)
        if process.returncode==0:browser=json.loads(process.stdout)
        write(project / "evidence" / (name + "-browser.json"),{"exit_code":process.returncode,"stdout":process.stdout,"stderr":process.stderr})
        actual["metrics"]["browser_exit_code"]=process.returncode
    return actual,payload,mermaid,browser


def display_resource(architecture, kind):
    """Compare an actual invocation or selected directory entry with its facts."""
    if kind == "node":
        record = next((node for node in architecture.get("workflow", {}).get("nodes", ())
                       if node.get("type_used") == IDS[kind]), {})
        return {**record, "effective_presentation":record.get("presentation", {})}
    key = "plugin_declaration:demo" if kind == "plugin" else kind + ":" + IDS[kind]
    return architecture.get("implementation_graph", {}).get("resources", {}).get(key, {})


def display_nodes(browser, kind):
    """Select the user's Node call or resource card, never a type/source card."""
    import re
    marker = "type_used: " + IDS[kind] if kind == "node" else "id: " + ("demo" if kind == "plugin" else IDS[kind])
    return [node for node in browser.get("nodes", ())
            if re.search(re.escape(marker) + r"(?=\s|$|rulesets:|status:|----------)", node["text"])]


def rgb(value):
    return "rgb(" + ", ".join(str(int(value[index:index+2],16)) for index in (1,3,5)) + ")"
