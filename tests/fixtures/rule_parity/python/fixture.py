"""Generate independent projects and collect actual public-entry diagnostics."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys


DEFAULT_CONTRACT = {
    "requires": [],
    "provides": [{"key": "demo.out", "type": "demo.out", "display_name": "Result"}],
    "input_semantics": {}, "output_semantics": {"demo.out": ["result value"]},
    "examples": [{"inputs": {}, "params": {}}],
}
DEFAULT_SOURCE = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n'


def _legacy_contract(contract):
    def requirement(item):
        return f'DataRequirement({item["type"]!r}, {item["cardinality"]!r}, display_name={item["display_name"]!r})'
    def provider(item):
        return f'DataProvider({item["key"]!r}, {item["type"]!r}, display_name={item["display_name"]!r})'
    def values(items, make):
        return "(" + ",".join(make(item) for item in items) + ("," if items else "") + ")"
    semantics = lambda value: {key: tuple(items) if isinstance(items, list) else items for key, items in value.items()}
    return "NodeContract(" + ",".join((
        "requires=" + values(contract.get("requires", []), requirement),
        "provides=" + values(contract.get("provides", []), provider),
        "input_semantics=" + repr(semantics(contract.get("input_semantics", {}))),
        "output_semantics=" + repr(semantics(contract.get("output_semantics", {}))),
        "examples=" + repr(tuple(contract.get("examples", []))),
    )) + ")"


def _declaration(spec, contract, *, type_key="parity.node", class_name="DemoNode", ref="node.py"):
    declaration = {
        "kind": "node", "type_key": type_key, "display_name": "Parity", "category": "parity",
        "description": "One rule parity observation.", "version": "1.0", "flow_kind": spec.get("flow_kind", "process"),
        "rulesets": spec.get("rulesets", ["vibeflow.process"]), "contract": contract,
        "implementations": [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": ref, "export": class_name}}],
    }
    declaration.update(spec.get("node_fields", {}))
    return declaration


def _adapt_source(source, descriptor, spec):
    if not spec.get("baseline_metadata", True):
        return source
    info_expression = "NodeInfo(" + ",".join(repr(descriptor[name]) for name in (
        "type_key", "display_name", "category", "description", "version", "flow_kind"))
    info_expression += ",external=" + repr(descriptor.get("external", False)) + ")"
    metadata = "    NODE_INFO=" + spec.get("legacy_info_expression", info_expression) + "\n"
    if spec.get("baseline_contract", True):
        contract_expression = spec.get("legacy_contract_expression")
        metadata += "    CONTRACT=" + (contract_expression if contract_expression is not None else _legacy_contract(descriptor["contract"])) + "\n"
    class_name = descriptor["implementations"][0]["source"]["export"]
    source = re.sub(r"^(class " + re.escape(class_name) + r"(?:\([^\n]*\))?:\n)",
        lambda match: match.group(0) + metadata, source, flags=re.MULTILINE)
    prefix = "from vibeflow.targets.python.nodetypes.protocols import NodeInfo, NodeContract\nfrom vibeflow.core import DataProvider, DataRequirement\n"
    if source.startswith("from __future__ import annotations\n"):
        return source.replace("from __future__ import annotations\n", "from __future__ import annotations\n" + prefix, 1)
    return prefix + source


def _write_project(root, variant, spec):
    contract = deepcopy(DEFAULT_CONTRACT)
    contract.update(deepcopy(spec.get("contract", {})))
    descriptor = _declaration(spec, contract)
    source = spec.get("source", DEFAULT_SOURCE).replace("__MARKER__", repr(str(root / "marker.txt")))
    if variant == "baseline":
        source = _adapt_source(source, descriptor, spec)
    else:
        descriptor.pop("category", None)
        if "category" in spec.get("node_fields", {}):
            descriptor["category"] = spec["node_fields"]["category"]
    manifests = root / "manifests/nodes" if variant == "baseline" else None
    resources = [descriptor]
    if variant == "baseline":
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / "node.jsonc").write_text(json.dumps(descriptor), encoding="utf-8")
    (root / "node.py").write_text(source, encoding="utf-8")
    if spec.get("registered_other_node"):
        resources.append(_write_other_node(root, variant, manifests, spec))
    if spec.get("entrypoint") in {"target.validate_graph_health", "cli.run"}:
        resources.extend(_write_boundaries(root, variant, manifests))
    if variant == "baseline":
        (root / "vibeflow_project.jsonc").write_text(json.dumps({
            "project_target": "python", "descriptors": {"nodes": ["manifests/nodes"]},
        }), encoding="utf-8")
    if spec.get("entrypoint") == "cli.run":
        resources.extend(_write_run_project(root, variant))
    files = dict(spec.get("files", {}))
    if spec.get("library_chain"):
        files.update(_chain_files(spec["library_chain"]))
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace("__MARKER__", repr(str(root / "marker.txt"))), encoding="utf-8")
    policy = deepcopy(spec.get("current_policy", spec.get("policy", {})) if variant == "current" else spec.get("policy", {}))
    if "base_lib" in policy and variant == "baseline":
        policy["base_lib"]["allowed_paths"] = [str(root / value) for value in policy["base_lib"].get("allowed_paths", [])]
    if variant == "current":
        _write_current_plugin(root, spec, resources, files)
    (root / "policy.jsonc").write_text(json.dumps({"policy": policy}), encoding="utf-8")
    if "general_source" in spec:
        (root / "source.py").write_text(spec["general_source"], encoding="utf-8")


def _write_run_project(root, variant):
    """Use formal runtime assembly, with import-only selection in the new kernel."""
    declarations = []
    project = {"project_target": "python"}
    if variant == "baseline":
        project["registry"] = "registry.py:register_nodes"
        registry = 'from vibeflow.targets.python.project import NodeRegistry\nfrom node import DemoNode\nfrom start import DemoNode as StartNode\nfrom end import DemoNode as EndNode\ndef register_nodes():\n    registry=NodeRegistry()\n'
        for type_key, name in (("node", "DemoNode"), ("start", "StartNode"), ("end", "EndNode")):
            registry += f"    registry.register('parity.{type_key}',{name},config_schema={{}},config_defaults={{}})\n"
        (root / "registry.py").write_text(registry + "    return registry\n", encoding="utf-8")
    else:
        declarations.append({"kind": "ruleset", "id": "parity.import_only",
            "calls": [{"id":"import", "rule_id":"vibeflow.import_side_effects", "params":{"effect_scope":"none"}}],
            "entrypoints":{"import":["import"], "static":[], "run":[]}})
    if variant == "baseline":
        (root / "vibeflow_project.jsonc").write_text(json.dumps(project), encoding="utf-8")
    (root / "workspace.jsonc").write_text(json.dumps({"roots": [{"id": "project", "path": "."}]}), encoding="utf-8")
    calls = [{"id": name, "type_used": "parity." + ("node" if name == "demo" else name),
        "display_name": name.title(), "description": "Runtime import parity call."} for name in ("start", "demo", "end")]
    (root / "workflow.jsonc").write_text(json.dumps({"pipeline": {"nodes": calls,
        "edges": [["start", "demo"], ["demo", "end"]]}}), encoding="utf-8")

    return declarations


def _write_boundaries(root, variant, manifests):
    declarations = []
    contract = {"requires": [], "provides": [], "input_semantics": {}, "output_semantics": {}, "examples": [{"inputs": {}, "params": {}}]}
    for name in ("start", "end"):
        descriptor = _declaration({"flow_kind": "terminal"}, contract, type_key="parity." + name, ref=name + ".py")
        source = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {}\n'
        if variant == "baseline":
            source = _adapt_source(source, descriptor, {})
        else:
            descriptor.pop("category", None)
        (root / (name + ".py")).write_text(source, encoding="utf-8")
        declarations.append(descriptor)
        if variant == "baseline":
            (manifests / (name + ".jsonc")).write_text(json.dumps(descriptor), encoding="utf-8")

    return declarations


def _write_other_node(root, variant, manifests, spec):
    contract = {"requires": [], "provides": [], "input_semantics": {}, "output_semantics": {}, "examples": [{"inputs": {}, "params": {}}]}
    ref = spec.get("other_node_ref", "node.py")
    descriptor = _declaration({}, contract, type_key="parity.other", class_name="OtherNode", ref=ref)
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.read_text() if ref == "node.py" else 'class OtherNode:\n    _private=7\n    def run_pure(self, inputs, params):\n        return {}\n'
    if ref != "node.py":
        (path.parent / "__init__.py").write_text("")
    if variant == "baseline":
        source = _adapt_source(source, descriptor, {})
    else:
        descriptor.pop("category", None)
    path.write_text(source, encoding="utf-8")
    if variant == "baseline":
        (manifests / "other.jsonc").write_text(json.dumps(descriptor), encoding="utf-8")
    return descriptor


def _chain_files(options):
    package, length = options["package"], options.get("length", 4)
    files = {package + "/__init__.py": ""}
    for number in range(length):
        imported = "." if options.get("relative") else package + "."
        prefix = f"from {imported}m{number + 1} import step\n" if number + 1 < length else ""
        body = "    return step(value)\n" if number + 1 < length else "    return value\n"
        extra = "\ndef extra_one():\n    return 1\n\ndef extra_two():\n    return 2\n" if number == 0 and options.get("extra_functions") else ""
        files[f"{package}/m{number}.py"] = prefix + "\ndef step(value):\n" + body + extra
    return files


def _write_current_plugin(root, spec, resources, files):
    """Author current inputs as fixed SDK declarations; never convert old files."""
    import runpy
    write_plugin = runpy.run_path(str(Path(__file__).resolve().parents[4] / "tests/fixtures/support/plugins.py"))["write_plugin"]
    library_paths = []
    standalone = spec.get("entrypoint") == "target.scan_base_lib"
    package = spec.get("library_chain", {}).get("package")
    if standalone:
        library_paths = [name for name in files if name.endswith(".py")]
    elif package:
        library_paths = [name for name in files if name.startswith(package + "/") and name.endswith(".py")]
    else:
        library_paths = list(spec.get("library_files", ()))
    node = resources[0]
    if library_paths:
        entry = next((name for name in library_paths if not name.endswith("__init__.py")), library_paths[0])
        resources.append({"kind":"base_lib", "id":"parity.library", "display_name":"Library",
            "description":"An explicitly declared library", "rulesets":["vibeflow.base_lib"],
            "implementations":[{"language":"python", "targets":["python"], "source":{"kind":"file","ref":entry},
                "implementation_files":[{"kind":"file","ref":name} for name in library_paths if name != entry]}]})
        node["base_libs"] = ["parity.library"]
    other_entries = {item["implementations"][0]["source"]["ref"] for item in resources if item["kind"] == "node"}
    support = [name for name in files if name.endswith(".py") and name not in library_paths and name not in other_entries]
    node["implementations"][0]["implementation_files"] = [{"kind":"file","ref":name} for name in support]
    if spec.get("entrypoint") == "cli.run":
        for item in resources:
            if item["kind"] == "node":
                item["rulesets"] = ["parity.import_only"] if item["type_key"] == "parity.node" else []
    selection = write_plugin(root, resources, target="python", plugin_id="parity.resources")
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python"}))
    workflow = root / "workflow.jsonc"
    data = json.loads(workflow.read_text()) if workflow.is_file() else {"rulesets":[], "pipeline":{"nodes":[{
        "id":"demo", "type_used":"parity.node", "display_name":"Demo", "description":"Source rule observation"}]}}
    data["plugins"] = [selection]
    workflow.write_text(json.dumps(data))


def _library_rule_script():
    return '''import json,sys
from pathlib import Path
from vibeflow.tooling.application.python.project.declarations import declared_python_registry
from vibeflow.tooling.project.workspace_loader import load_project_workspace
from vibeflow.targets.python.project.resource_rules import review_python_resource
from vibeflow.targets.python.rules.node.policy import PurityPolicy
root=Path(sys.argv[1]); options=json.loads(sys.argv[2])
registry=declared_python_registry(load_project_workspace(root/"workflow.jsonc"),config_path=root/"workflow.jsonc")
registry.configure_rule_defaults(purity_policy=PurityPolicy(**options))
findings=[item.to_dict() for declaration in registry.loaded_plugins.catalogs.base_libs
    for phase in ("import","static") for item in review_python_resource(declaration,base_path=root,registry=registry,phase=phase)]
print(json.dumps({"base_lib":{"findings":findings,"modules":[item.id for item in registry.loaded_plugins.catalogs.base_libs]}}))
'''


def _command(root, variant, spec):
    entrypoint = spec.get("entrypoints", {}).get(variant, spec.get("entrypoint", "cli.inspect-node"))
    if entrypoint == "cli.quality-check":
        return [sys.executable, "-m", "vibeflow", "quality-check", "--path", str(root / "source.py"), "--json", *spec.get("cli_args", [])]
    if entrypoint == "cli.run":
        return [sys.executable, "-m", "vibeflow", "run", "--config", str(root / "workflow.jsonc"),
            "--workspace", str(root / "workspace.jsonc"), "--run-root", str(root / "runs"), "--run-id", "import-marker"]
    if entrypoint == "cli.inspect-node":
        return [sys.executable, "-m", "vibeflow", "inspect-node", "--type", "parity.node", "--module", str(root / "node.py"),
            "--class", "DemoNode", "--policy", str(root / "policy.jsonc"), *(["--config", str(root / "workflow.jsonc")] if variant == "current" else [])]
    scripts = {"target.scan_base_lib": lambda: _base_lib_script(variant), "target.analyze_python_source": lambda: _source_script(variant),
        "target.validate_node_class": _class_validation_script}
    script = scripts[entrypoint]() if entrypoint in scripts else _graph_script(variant)
    options = deepcopy(spec.get("source_options", {}) if entrypoint == "target.analyze_python_source" else spec.get("purity_kwargs", {}))
    if variant == "current":
        options = deepcopy(spec.get("current_purity_kwargs", options))
    return [sys.executable, "-c", script, str(root), json.dumps(options)]


def _base_lib_script(variant):
    if variant == "current":
        return _library_rule_script()
    return '''import json,sys
from pathlib import Path
from vibeflow.targets.python.project import scan_base_lib
from vibeflow.targets.python.quality.source_analysis import PurityPolicy
root=Path(sys.argv[1]); options=json.loads(sys.argv[2])
options['allowed_base_lib_paths']=(str(root/'base_lib'),)
report=scan_base_lib(root,policy=PurityPolicy(**options))
print(json.dumps({'base_lib':report.to_dict()}))
'''


def _class_validation_script():
    return '''import json,sys
from pathlib import Path
from vibeflow.tooling.application.python.cli.node import load_node_class
from vibeflow.targets.python.quality.source_analysis import validate_node_class,PurityPolicy
root=Path(sys.argv[1]); node=load_node_class(root/'node.py',node_type='parity.node',class_name='DemoNode')
violations=validate_node_class(node,expected_type='parity.node',scan_module=True,policy=PurityPolicy(**json.loads(sys.argv[2])))
def item(v):
    return {'rule_id':v.rule_id,'severity':v.severity,'message':v.message,'source_location':dict(v.source_location)}
errors=[item(v) for v in violations if v.severity=='error']; warnings=[item(v) for v in violations if v.severity!='error']
print(json.dumps({'health':{'status':'FAIL' if errors else 'CONCERNS' if warnings else 'PASS','errors':errors,'warnings':warnings}}))
'''


def _graph_script(variant):
    setup = '''from vibeflow.tooling.application.python.cli.node import load_node_class
registry=NodeRegistry(); node=load_node_class(root/'node.py',node_type='parity.node',class_name='DemoNode')
declaration=json.loads((root/'manifests/nodes/node.jsonc').read_text())
registry.register('parity.node',node,config_schema=declaration['contract'].get('params_schema',{}),config_defaults=declaration['contract'].get('params_defaults',{}))
for name in ('start','end'):
    registry.register('parity.'+name,load_node_class(root/(name+'.py'),node_type='parity.'+name,class_name='DemoNode'),config_schema={},config_defaults={})
other_path=root/'manifests/nodes/other.jsonc'
if other_path.exists():
    declaration=json.loads(other_path.read_text())
    reference=declaration['implementations'][0]['source']['ref']
    if reference=='node.py':
        other=load_node_class(root/reference,node_type='parity.other',class_name='OtherNode')
    else:
        from importlib import import_module
        other=getattr(import_module(reference.removesuffix('.py').replace('/','.')),'OtherNode')
    registry.register('parity.other',other,config_schema={},config_defaults={})
report=validate_graph_health(graph,registry=registry,purity_policy=policy)
''' if variant == "baseline" else '''from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_workflow_source_context
from vibeflow.tooling.project.workspace_loader import load_project_workspace
registry=declared_python_registry(load_project_workspace(root/'node.py'),config_path=root/'workflow.jsonc')
report=validate_graph_health(graph,registry=registry,purity_policy=policy,source_context=collect_workflow_source_context(registry,graph))
'''
    policy_module = "vibeflow.targets.python.quality.source_analysis" if variant == "baseline" else "vibeflow.targets.python.rules.node.policy"
    return '''import json,sys
from pathlib import Path
from vibeflow.core import GraphConfig,NodeSpec,EdgeSpec,DataProvider
from vibeflow.core.flow import NodeMetadata
from vibeflow.targets.python.project import NodeRegistry
''' + "from " + policy_module + " import PurityPolicy\n" + '''from vibeflow.targets.python.quality.workflow import validate_graph_health
root=Path(sys.argv[1]); policy=PurityPolicy(**json.loads(sys.argv[2]))
def call(name):
    return NodeSpec(id=name,type_used='parity.'+(name if name!='demo' else 'node'),metadata=NodeMetadata(name,'Parity graph call'),provides=(DataProvider('demo.out','demo.out',display_name='Result'),) if name=='demo' else ())
graph=GraphConfig(nodes=tuple(call(name) for name in ('start','demo','end')),edges=(EdgeSpec('start','demo'),EdgeSpec('demo','end')))
''' + setup + "print(json.dumps({'health':report.to_dict()}))\n"


def _source_script(variant):
    if variant == "current":
        return '''import json,sys
from pathlib import Path
from vibeflow.targets.python.quality import PythonSource,analyze_python_source
from vibeflow.tooling.application.python.project.quality_scan import scan_code_quality
root=Path(sys.argv[1]); options=json.loads(sys.argv[2]); path=root/'source.py'
result=analyze_python_source(PythonSource(module=options.get('module','pkg.source'),relative_path='source.py',source_path=str(path),text=path.read_text()))
findings=list(result.findings)
if options.get('check_side_effects',False):
    review=scan_code_quality(path,check_side_effects=True)
    findings.extend(item for item in review.findings if item.code.startswith('QUALITY.SIDE_EFFECT.'))
file=result.file; functions=file.functions
metrics={'file':file.to_dict(),'fingerprints_equal':len(functions)==2 and functions[0].ast_fingerprint==functions[1].ast_fingerprint,
    'required_params_first':functions[0].param_count if functions else 0,
    'relative_import_resolved':'pkg.helper' in file.imports,
    'first_import_line':file.import_sites[0].line if file.import_sites else 0}
print(json.dumps({'source_facts':metrics,'findings':[finding.to_dict() for finding in findings]}))
'''
    return '''import json,sys
from pathlib import Path
from vibeflow.targets.python.quality import PythonSource,analyze_python_source
root=Path(sys.argv[1]); options=json.loads(sys.argv[2]); path=root/'source.py'
result=analyze_python_source(PythonSource(module=options.get('module','pkg.source'),relative_path='source.py',source_path=str(path),text=path.read_text()),check_side_effects=options.get('check_side_effects',False))
file=result.file; functions=file.functions
metrics={'file':file.to_dict(),'fingerprints_equal':len(functions)==2 and functions[0].ast_fingerprint==functions[1].ast_fingerprint,
    'required_params_first':functions[0].param_count if functions else 0,
    'relative_import_resolved':'pkg.helper' in file.imports,
    'first_import_line':file.import_sites[0].line if file.import_sites else 0}
print(json.dumps({'source_facts':metrics,'findings':[finding.to_dict() for finding in result.findings]}))
'''


def _actual(result, root, *, process_exception_observation=False):
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        if process_exception_observation and result.returncode:
            return {"status":"ERROR","codes":[],"positions":[],"metrics":{"exit_code":result.returncode,
                "marker":"", "transport":"uncaught_exception"},"message":result.stderr or result.stdout,"exit_code":result.returncode}
        return {"status": "ERROR", "codes": [{"code": "PARITY.ENTRYPOINT.ERROR", "severity": "error"}],
            "positions": [], "metrics": {}, "message": result.stderr or result.stdout, "exit_code": result.returncode}
    health = payload.get("health", {})
    findings = [*health.get("errors", []), *health.get("warnings", [])]
    findings.extend(payload.get("base_lib", {}).get("findings", []))
    if not health:
        findings.extend(payload.get("findings", []))
        findings.extend([*payload.get("errors", []), *payload.get("warnings", [])])
    codes, positions = [], []
    for item in findings:
        code = item.get("code", item.get("rule_id", ""))
        codes.append({"code": code, "severity": item.get("severity", "error")})
        positions.append({"code": code, **item.get("source_location", {})})
    node = payload.get("node", {})
    metrics = {**node.get("metrics", {}), "effect_scope": node.get("effect_scope"),
        "dependency_chain": payload.get("base_lib_dependency_chain", {}),
        "node_metrics": health.get("info", {}).get("node_metrics", {}),
        "base_lib_modules": payload.get("base_lib", {}).get("modules", []),
        **payload.get("source_facts", {}), "quality_files": payload.get("files", [])}
    marker = root / "marker.txt"
    marker_text = marker.read_text(encoding="utf-8") if marker.exists() else ""
    metrics.update(marker=marker_text, exit_code=result.returncode)
    return {"status": health.get("status", payload.get("status", "FAIL" if any(item["severity"] == "error" for item in codes) else "PASS")),
        "codes": codes, "positions": positions, "metrics": metrics,
        "message": "\n".join(item.get("message", "") for item in findings), "exit_code": result.returncode,
        "marker": marker_text, "payload": payload}


def observe(work_root, variant, spec):
    root = work_root / spec["id"].replace(".", "_")
    root.mkdir(parents=True, exist_ok=True)
    _write_project(root, variant, spec)
    command = _command(root, variant, spec)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=30)
    expected = deepcopy(spec["expected"])
    expected.update(expected.pop("variants", {}).get(variant, {}))
    entrypoint = spec.get("entrypoints", {}).get(variant,spec.get("entrypoint", "cli.inspect-node"))
    if entrypoint.startswith("cli."):
        expected.setdefault("metrics", {}).setdefault("exit_code", 0 if expected["should_accept"] else 1)
    return {"id": spec["id"], "title": spec["title"], "family": spec["family"], "expected": expected,
        "actual": _actual(result, root,process_exception_observation=spec.get("process_exception_observation",False)), "classification": spec.get("classification", "preserved"),
        "notes": spec.get("notes", ""), "evidence": {"entrypoint": entrypoint,
            "project": str(root), "command": command, "baseline_source": spec.get("baseline_source", "")}}
