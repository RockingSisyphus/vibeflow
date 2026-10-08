"""Author and edit fixed SDK plugins for regression projects.

Inputs are explicit canonical resource declarations. This helper performs no
registration discovery, registry parsing, bundle expansion or metadata repair.
"""
from dataclasses import dataclass
import ast
import json
from pathlib import Path
import pprint
import re
import shutil

_CONSTRUCTORS = {"node": "node", "rule": "rule", "ruleset": "ruleset",
    "data_schema": "data_schema", "base_lib": "base_lib", "capability": "capability",
    "host_extension": "host_extension"}
_JAVASCRIPT_CONSTRUCTORS = {"defineNode": "node", "defineRule": "rule",
    "defineRuleset": "ruleset", "defineDataSchema": "data_schema", "defineBaseLib": "base_lib",
    "defineCapability": "capability", "defineHostExtension": "host_extension"}


def plugin_file(project):
    project = Path(project)
    return next((project / name for name in ("code_plugin.py", "code_plugin.ts")
                 if (project / name).is_file()), project / "code_plugin.py")


def resource_declarations(project):
    """Read the literal SDK definitions authored by this fixture helper."""
    path = plugin_file(project)
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
                values.append({"kind": call.func.id, **fields})
            elif isinstance(call.func, ast.Name) and call.func.id == "ResourceDefinition":
                values.append(ast.literal_eval(call.args[0].args[0]))
    else:
        text = path.read_text()
        for match in re.finditer(r"export const resource_\d+\s*=\s*(define\w+)\(", text):
            fields, _ = json.JSONDecoder().raw_decode(text[match.end():])
            kind = _JAVASCRIPT_CONSTRUCTORS.get(match.group(1))
            values.append({"kind": kind, **fields} if kind else fields)
    return values


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
                        filename=path.name, plugin_id=_plugin_id(path))


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


def copy_sdk_inputs(source, destination):
    """Copy a fixed SDK fixture overlay; historical inputs are never loaded."""
    repository = Path(__file__).resolve().parents[3]
    fixture = repository / "tests/fixtures/sdk_resources" / Path(source).resolve().relative_to(repository)
    if fixture.is_dir():
        shutil.copytree(fixture, destination, dirs_exist_ok=True)

def write_plugin(project, values, *, target, filename=None, plugin_id="fixture.resources"):
    """Fixed definitions with explicit delayed implementation locators."""
    project = Path(project)
    filename = filename or ("code_plugin.py" if target == "python" else "code_plugin.ts")
    constructors = {"node": "node", "rule": "rule", "ruleset": "ruleset", "data_schema": "data_schema",
                    "base_lib": "base_lib", "capability": "capability", "host_extension": "host_extension"}
    lines, names = [], []
    for index, entry in enumerate(values):
        payload = dict(entry[1] if isinstance(entry, tuple) else entry)
        kind = payload.pop("kind")
        name = "resource_" + str(index)
        names.append(name)
        if target == "python":
            if kind not in constructors:
                expression = f"ResourceDefinition(decode_resource({pprint.pformat({'kind':kind, **payload}, sort_dicts=False)}))"
            else:
                if kind in {"node", "rule", "base_lib"}:
                    payload["source"] = payload["implementations"][0]["source"]
                expression = f"{constructors[kind]}(**{pprint.pformat(payload, sort_dicts=False)})"
            lines.append(f"{name} = {expression}")
        else:
            mapping = {"node":"defineNode", "rule":"defineRule", "ruleset":"defineRuleset",
                "data_schema":"defineDataSchema", "base_lib":"defineBaseLib", "capability":"defineCapability", "host_extension":"defineHostExtension"}
            constructor = mapping.get(kind, "defineResource")
            lines.append(f"export const {name} = {constructor}({json.dumps({'kind':kind, **payload} if constructor == 'defineResource' else payload)});")
    if target == "python":
        prefix = "from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,data_schema,base_lib,capability,host_extension,ResourceDefinition\nfrom vibeflow.core.descriptors.decode import decode_resource\n"
        lines.append(f"plugin = Plugin(id={plugin_id!r}, resources=[{', '.join(names)}])")
    else:
        prefix = 'import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension,defineResource} from "@vibeflow/plugin";\n'
        lines.append(f"export const plugin = definePlugin({{id:{json.dumps(plugin_id)}, resources:[{', '.join(names)}]}});")
    (project / filename).write_text(prefix + "\n\n".join(lines) + "\n")
    return {"source": {"kind": "file", "ref": filename, "export": "plugin"}}


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
    """Declare a lifecycle factory from an explicit implementation locator."""
    project = Path(project)
    if source["kind"] == "file":
        module = Path(source["ref"]).with_suffix("").as_posix().replace("/", ".")
    elif source["kind"] == "module":
        module = source["ref"]
    else:
        raise ValueError("Python lifecycle fixtures require file or module sources")
    export = source["export"]
    code = f'''from vibeflow.targets.python.sdk import Plugin

def create(context):
    from {module} import {export}
    instance = {export}()
    instance.config = context["config"]
    if hasattr(instance, "configure"):
        instance.configure(context["config"])
    return instance

plugin = Plugin(id={plugin_id!r}, {plugin_type}=create, priority={priority!r},
    display_name={plugin_id!r}, description="Native lifecycle fixture", version="1.0")
'''
    (project / filename).write_text(code)
    return {"source": {"kind": "file", "ref": filename, "export": "plugin"}, "config": config or {}}
