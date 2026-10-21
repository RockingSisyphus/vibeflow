"""Author and edit fixed SDK plugins for regression projects.

Inputs are explicit canonical resource declarations. This helper performs no
registration discovery, registry parsing, bundle expansion or metadata repair.
"""
from dataclasses import dataclass
import ast
from copy import deepcopy
import json
from pathlib import Path
import pprint
import os
import re
import shutil

_CONSTRUCTORS = {"node": "node", "rule": "rule", "ruleset": "ruleset",
    "data_schema": "data_schema", "base_lib": "base_lib", "capability": "capability",
    "node_type": "node_type"}
_JAVASCRIPT_CONSTRUCTORS = {"defineNode": "node", "defineRule": "rule",
    "defineRuleset": "ruleset", "defineDataSchema": "data_schema", "defineBaseLib": "base_lib",
    "defineCapability": "capability", "defineNodeType": "node_type"}


def plugin_file(project):
    project = Path(project)
    for name in ("code_plugin", "resources"):
        for extension in ("py", "ts"):
            path = project / "plugins" / name / ("plugin." + extension)
            if path.is_file():
                return path
    return project / "plugins/code_plugin/plugin.py"


def _literal_declarations(path):
    if not path.exists():
        return []
    values = []
    if path.suffix == ".py":
        for statement in ast.parse(path.read_text()).body:
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            if isinstance(call.func, ast.Name) and call.func.id in _CONSTRUCTORS:
                fields = {}
                for item in call.keywords:
                    if item.arg is None:
                        fields.update(ast.literal_eval(item.value))
                    else:
                        fields[item.arg] = ast.literal_eval(item.value)
                fields.pop("source", None)
                values.append({"kind": _CONSTRUCTORS[call.func.id], **fields})
            elif isinstance(call.func, ast.Name) and call.func.id == "ResourceDefinition":
                values.append(ast.literal_eval(call.args[0].args[0]))
    else:
        text = path.read_text()
        for match in re.finditer(r"export const resource_\d+\s*=\s*(define\w+)\(", text):
            fields, _ = json.JSONDecoder().raw_decode(text[match.end():])
            kind = _JAVASCRIPT_CONSTRUCTORS.get(match.group(1))
            values.append({"kind": kind, **fields} if kind else fields)
    return values


def resource_declarations(project):
    """Read fixture-authored declarations in the same ownership layout as products."""
    path = plugin_file(project)
    stem = path.parent.name
    paths = (path, *(Path(project) / group / (stem + "_declarations" + path.suffix)
                      for group in ("nodes", "base_lib")))
    result = []
    for source in paths:
        for value in _literal_declarations(source):
            for implementation in value.get("implementations", ()):
                if "implementation_files" not in implementation:
                    continue
                implementation["implementation_files"] = [
                    {**member, "ref": os.path.relpath(source.parent / member["ref"], project)}
                    if isinstance(member, dict) and member.get("kind") == "file" and not Path(member["ref"]).is_absolute()
                    else member for member in implementation.get("implementation_files", ())]
            result.append(value)
    return result


def _plugin_id(path):
    text = path.read_text()
    if path.suffix == ".py":
        for item in ast.walk(ast.parse(text)):
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "Plugin":
                return next(ast.literal_eval(field.value) for field in item.keywords if field.arg == "id")
    match = re.search(r"definePlugin\(\{\s*id\s*:\s*([\"'][^\"']+[\"'])", text)
    return ast.literal_eval(match.group(1)) if match else "fixture.resources"


def update_resources(project, values):
    path = plugin_file(project)
    return write_plugin(project, values, target="python" if path.suffix == ".py" else "javascript",
                        filename=path.parent.name + path.suffix, plugin_id=_plugin_id(path))


@dataclass(frozen=True)
class Resource:
    project: Path
    kind: str
    id: str

    @property
    def parent(self):
        return self.project

    def read_text(self, **kwargs):
        value = next(item for item in resource_declarations(self.project)
                     if item["kind"] == self.kind and item.get("type_key", item.get("id")) == self.id)
        return json.dumps(value)

    def write_text(self, text, **kwargs):
        value = json.loads(text)
        values = resource_declarations(self.project)
        index = next((index for index, item in enumerate(values) if item["kind"] == self.kind
                      and item.get("type_key", item.get("id")) == self.id), None)
        if index is None:
            values.append(value)
        else:
            values[index] = value
        update_resources(self.project, values)
        return len(text)

    def unlink(self):
        update_resources(self.project, [item for item in resource_declarations(self.project)
            if not (item["kind"] == self.kind and item.get("type_key", item.get("id")) == self.id)])

    def exists(self):
        return any(item["kind"] == self.kind and item.get("type_key", item.get("id")) == self.id
                   for item in resource_declarations(self.project))


def resource(project, kind, resource_id):
    return Resource(Path(project), kind, resource_id)


def append_resource(project, declaration):
    update_resources(project, [*resource_declarations(project), declaration])


def resources(project, kind=None):
    return [resource(project, item["kind"], item.get("type_key", item.get("id")))
            for item in resource_declarations(project) if kind is None or item["kind"] == kind]


def write_plugin(project, values, *, target, filename=None, plugin_id="fixture.resources"):
    """Author independent Nodes/BaseLibs and one atomic Plugin package."""
    project = Path(project)
    from tests.fixtures.support.projects import register_root
    project.mkdir(parents=True, exist_ok=True)
    register_root(project, target)
    suffix = ".py" if target == "python" else ".ts"
    stem = Path(filename or "code_plugin").stem
    package = project / "plugins" / stem
    package.mkdir(parents=True, exist_ok=True)
    groups = {"plugin": [], "nodes": [], "base_lib": []}
    for entry in values:
        payload = deepcopy(entry[1] if isinstance(entry, tuple) else entry)
        kind = payload["kind"]
        groups["nodes" if kind == "node" else "base_lib" if kind == "base_lib" else "plugin"].append(payload)
    python_names = "Plugin,node,node_type,rule,ruleset,data_schema,base_lib,capability,ResourceDefinition"
    javascript_names = "definePlugin,defineNode,defineNodeType,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineResource"
    for group, declarations in groups.items():
        path = package / ("plugin" + suffix) if group == "plugin" else project / group / (stem + "_declarations" + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines, names = [], []
        for index, payload in enumerate(declarations):
            payload = dict(payload)
            kind = payload.pop("kind")
            for implementation in payload.get("implementations", ()):
                if kind == "rule":
                    implementation.pop("implementation_files", None)
                    continue
                implementation["implementation_files"] = [
                    {**member, "ref": os.path.relpath(project / member["ref"], path.parent)}
                    if isinstance(member, dict) and member.get("kind") == "file" and not Path(member["ref"]).is_absolute()
                    else member for member in implementation.get("implementation_files", ())]
            name = "resource_" + str(index)
            names.append(name)
            if target == "python":
                if kind not in _CONSTRUCTORS:
                    expression = f"ResourceDefinition(decode_resource({pprint.pformat({'kind':kind, **payload}, sort_dicts=False)}))"
                else:
                    if kind in {"node", "rule", "base_lib"} and payload.get("implementations"):
                        payload["source"] = payload["implementations"][0]["source"]
                    expression = f"{_CONSTRUCTORS[kind]}(**{pprint.pformat(payload, sort_dicts=False)})"
                lines.append(f"{name} = {expression}")
            else:
                mapping = {kind: name for name, kind in _JAVASCRIPT_CONSTRUCTORS.items()}
                constructor = mapping.get(kind, "defineResource")
                lines.append(f"export const {name} = {constructor}({json.dumps({'kind':kind, **payload} if constructor == 'defineResource' else payload)});")
        if target == "python":
            prefix = f"from vibeflow.targets.python.sdk import {python_names}\nfrom vibeflow.core.descriptors.decode import decode_resource\n"
            if group == "plugin":
                lines.append(f"plugin = Plugin(id={plugin_id!r}, resources=[{', '.join(names)}])")
        else:
            prefix = f'import {{{javascript_names}}} from "@vibeflow/plugin";\n'
            if group == "plugin":
                lines.append(f"export const plugin = definePlugin({{id:{json.dumps(plugin_id)}, resources:[{', '.join(names)}]}});")
        path.write_text(prefix + "\n\n".join(lines) + "\n")
    return {"source": {"kind": "file", "ref": (package / ("plugin" + suffix)).relative_to(project).as_posix(), "export": "plugin"}}


def publish_native_fixture(config_path, registry, *, keys=None):
    """Author SDK resources from an explicitly supplied native test registry."""
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    from tests.fixtures.support.rule_inspection import write_registry_project
    config_path = Path(config_path)
    project = config_path.parent
    selection = write_registry_project(project, registry, registry.available() if keys is None else keys)
    data = dict(load_raw_config_document(config_path).data)
    selected = list(data.get("plugins", []))
    if selection not in selected:
        selected.insert(0, selection)
    data["plugins"] = selected
    config_path.write_text(json.dumps(data))


def write_lifecycle_fixture(project, *, source, plugin_id, plugin_type="runtime", config=None,
                            priority=100, filename="lifecycle_plugin.py"):
    """Author one package, including the supplied lifecycle implementation."""
    project = Path(project)
    if source["kind"] != "file":
        raise ValueError("fixture lifecycle implementation must be an explicit file")
    package = project / "plugins" / Path(filename).stem
    package.mkdir(parents=True, exist_ok=True)
    original = project / source["ref"]
    destination = package / original.name
    shutil.copyfile(original, destination)
    module = destination.stem
    export = source["export"]
    code = f'''from vibeflow.targets.python.sdk import Plugin
from .{module} import {export} as Implementation
def create(context):
    instance = Implementation()
    instance.config = context["config"]
    if hasattr(instance, "configure"):
        instance.configure(context["config"])
    return instance
plugin = Plugin(id={plugin_id!r}, {plugin_type}=create, priority={priority!r},
    display_name={plugin_id!r}, description="Native lifecycle fixture", version="1.0")
'''
    entry = package / "plugin.py"
    entry.write_text(code)
    return {"source": {"kind": "file", "ref": entry.relative_to(project).as_posix(), "export": "plugin"}, "config": config or {}}
