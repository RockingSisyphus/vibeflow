"""Emit code plugins from test data; no production JSONC registration bridge.

Historic cases may keep declarative input data for mutation and audit. This
fixture writer turns that data into the same fixed SDK code users load, before
invoking any VibeFlow entrypoint. It is not imported by VibeFlow.
"""

import ast
import json
from pathlib import Path
import pprint
import os
import shutil

from vibeflow.tooling.project.config_loader import load_raw_config_document


def copy_archival_inputs(source, destination):
    """Restore frozen mutation inputs only inside a temporary regression case."""
    repository = Path(__file__).resolve().parents[3]
    archive = repository / "tests/fixtures/resource_migration" / Path(source).resolve().relative_to(repository)
    if archive.is_dir():
        shutil.copytree(archive, destination, dirs_exist_ok=True)


def resource_inputs(project):
    project = Path(project)
    document = load_raw_config_document(project / "vibeflow_project.jsonc").data
    values, visited = [], set()
    def read(path):
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)
        data = load_raw_config_document(path).data
        if data.get("kind") == "bundle":
            for refs in data["resources"].values():
                for ref in refs:
                    add(path.parent / ref)
        else:
            values.append((path, data))
    def add(path):
        if not path.exists():
            values.append((path, {"kind":"fixture_missing", "ref":str(path)}))
            return
        if path.is_dir():
            for item in sorted(path.rglob("*.jsonc")):
                read(item)
        else:
            read(path)
    roots_file = project / ".fixture-resource-roots.json"
    remembered = json.loads(roots_file.read_text()) if roots_file.is_file() else {}
    fallback_roots = remembered.pop("fixture_roots", None)
    groups = {**remembered, **document.get("descriptors", {})}
    if groups and (project / "bundles").is_dir() and "bundles" not in groups:
        groups["bundles"] = ["bundles"]
    if groups:
        roots_file.write_text(json.dumps({**groups, **({"fixture_roots": fallback_roots} if fallback_roots else {})}))
    if groups:
        for refs in groups.values():
            for ref in refs:
                add(project / ref)
    if not groups or fallback_roots:
        # Historical mutation fixtures retain their inputs outside the public
        # plugin loading protocol. This test helper alone reads those inputs.
        for folder in ("bundles", "manifests", "bundle", "negative/manifests"):
            directory = project / folder
            if directory.is_dir():
                for path in sorted(directory.rglob("*.jsonc")):
                    data = load_raw_config_document(path).data
                    if data.get("kind") in {"node", "rule", "ruleset", "data_schema", "base_lib", "capability", "host_extension", "plugin", "bundle"}:
                        key = (data.get("kind"), data.get("id",data.get("type_key")))
                        if folder != "bundles" and any((value.get("kind"), value.get("id",value.get("type_key"))) == key and value == data for _,value in values):
                            continue
                        read(path)
        roots_file.write_text(json.dumps({**groups,"fixture_roots":[folder for folder in ("bundles","manifests","bundle","negative/manifests") if (project / folder).is_dir()]}))
    registry = project / "registry.py"
    if registry.is_file():
        for item in ast.walk(ast.parse(registry.read_text())):
            if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Attribute) or item.func.attr != "register" or not item.args:
                continue
            try:
                resource_id = ast.literal_eval(item.args[0])
                fields = {arg.arg: ast.literal_eval(arg.value) for arg in item.keywords}
            except (ValueError, TypeError):
                continue
            if "module" not in fields:
                continue
            kind = "plugin" if "class_name" in fields else "base_lib"
            module = fields.pop("module")
            source = {"kind": "file" if module.endswith(".py") or "/" in module else "module", "ref": module}
            data = {"kind": kind, "id": resource_id,
                "display_name": fields.pop("display_name", resource_id),
                "description": fields.pop("description", resource_id),
                "rulesets": ["vibeflow.plugin" if kind == "plugin" else "vibeflow.base_lib"]}
            if kind == "plugin":
                source["export"] = fields.pop("class_name")
                data.update(type=fields.pop("plugin_type", "runtime"), targets=["python"])
            data.update(fields, implementations=[{"language": "python", "targets": ["python"], "source": source}])
            # These legacy fixture implementations used metadata constants for
            # discovery. The new fixed plugin owns that data; retain all other
            # statements, including the behavior under review.
            implementation_path = project / (source["ref"] if source["kind"] == "file" else source["ref"].replace(".", "/") + ".py")
            if implementation_path.is_file():
                text = implementation_path.read_text()
                lines = text.splitlines(keepends=True)
                try:
                    for statement in ast.walk(ast.parse(text)):
                        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                            targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                            if any(isinstance(target, ast.Name) and target.id in {"PLUGIN_INFO", "BASE_LIB_INFO"} for target in targets):
                                for line in range(statement.lineno - 1, statement.end_lineno):
                                    lines[line] = "\n"
                    implementation_path.write_text("".join(lines))
                except SyntaxError:
                    pass  # The actual Rule must report invalid source.
            if not any(value.get("kind") == kind and value.get("id") == resource_id for _, value in values):
                values.append((registry, data))
    return values


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
        if kind == "fixture_missing":
            missing = Path(payload["ref"]).resolve().with_suffix(".py" if target == "python" else ".ts")
            if target == "python":
                relative = missing.relative_to(project).with_suffix("")
                if len(relative.parts) > 1:
                    package = project / relative.parts[0]
                    package.mkdir(exist_ok=True)
                    (package / "__init__.py").touch()
                lines.append("import " + ".".join(relative.parts))
            else:
                lines.append("import " + json.dumps("./" + missing.relative_to(project).as_posix()) + ";")
            continue
        name = "resource_" + str(index)
        names.append(name)
        if target == "python":
            if kind not in constructors:
                # Lifecycle descriptors are internal resources; the fixture
                # declares their delayed factory through the same builder.
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


def migrate_fixture(project, *, configs=None):
    """One-shot test preparation. Subsequent edits must explicitly regenerate."""
    project = Path(project)
    path = project / "vibeflow_project.jsonc"
    document = dict(load_raw_config_document(path).data)
    inputs = resource_inputs(project)
    target = document["project_target"]
    toolchain = os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT")
    if target == "javascript" and toolchain and not (project / "node_modules").exists():
        (project / "node_modules").symlink_to(Path(toolchain) / "node_modules", target_is_directory=True)
    selection = write_plugin(project, [(path, data) for path, data in inputs if data.get("kind") != "plugin"], target=target)
    lifecycle_sources = {}
    for index, (location, descriptor) in enumerate(inputs):
        if descriptor.get("kind") != "plugin":
            continue
        name = "code_lifecycle_" + str(index) + (".py" if target == "python" else ".ts")
        if target == "python":
            factory = descriptor["implementations"][0]["source"]
            if factory["kind"] == "module":
                body = f"    from {factory['ref']} import {factory['export']}\n    instance = {factory['export']}()\n"
            else:
                module_name = factory["ref"].removesuffix(".py").replace("/", ".")
                body = f"    from {module_name} import {factory['export']}\n    instance = {factory['export']}()\n"
            text = 'from vibeflow.targets.python.sdk import Plugin\n\ndef create(context):\n' + body + '    if hasattr(instance, "configure"):\n        instance.configure(context["config"])\n    return instance\n\n'
            text += f"plugin = Plugin(id={descriptor['id']!r}, {descriptor['type']}=create, rulesets={tuple(descriptor.get('rulesets', []))!r}, display_name={descriptor.get('display_name',descriptor['id'])!r}, description={descriptor.get('description','')!r}, version={descriptor.get('version','')!r})\n"
            (project / name).write_text(text)
            lifecycle_sources.setdefault(descriptor["id"], []).append({"source": {"kind":"file", "ref":name, "export":"plugin"}})
        else:
            lifecycle_sources.setdefault(descriptor["id"], []).append(write_plugin(project, [(location, descriptor)], target=target,
                filename=name, plugin_id=descriptor["id"] + ".fixture." + str(index)))

    for removed in ("descriptors", "registry", "base_lib", "plugins"):
        document.pop(removed, None)
    path.write_text(json.dumps(document, indent=2) + "\n")
    paths = configs or sorted({*project.rglob("*.jsonc"), *project.rglob("*.json")})
    lifecycle = {data["id"] for _, data in inputs if data.get("kind") == "plugin"}
    for config in paths:
        try:
            data = dict(load_raw_config_document(config).data)
        except ValueError:
            continue  # Preserve malformed source for its formal diagnostic.
        if "pipeline" not in data:
            continue
        previous = data.get("plugins", [])
        # Tests specify lifecycle configuration independently of fixed resource
        # definitions. Copy values into the selected package context.
        options = {}
        for item in previous:
            if isinstance(item, dict) and item.get("id") in lifecycle:
                options.update(item.get("config", {}))
        data["plugins"] = [selection]
        for item in previous:
            if isinstance(item, str):
                item = {"id": item}
            if isinstance(item, dict) and item.get("id") in lifecycle_sources:
                data["plugins"].extend({**source, **{key: value for key, value in item.items() if key in {"config", "enabled", "status"}},
                    **({"id": item["id"]} if item.get("status") == "planned" else {})} for source in lifecycle_sources[item["id"]])
            elif isinstance(item, dict) and item.get("status") == "planned":
                data["plugins"].append(item)
            elif isinstance(item, dict) and item.get("source", {}).get("ref") == selection["source"]["ref"]:
                continue
            elif isinstance(item, dict):
                data["plugins"].append(item)

        config.write_text(json.dumps(data, indent=2) + "\n")
    return inputs


def prepare_workspace_fixture(workspace_path):
    """Explicitly publish fixture inputs as SDK plugins before a test call."""
    workspace_path = Path(workspace_path)
    if not workspace_path.is_file():
        return
    raw = load_raw_config_document(workspace_path).data
    roots = raw.get("roots", [])
    selections = []
    selection_targets = {}
    for root in roots:
        if not isinstance(root, dict) or not root.get("path"):
            continue
        project = (workspace_path.parent / root["path"]).resolve()
        if not (project / "vibeflow_project.jsonc").is_file():
            continue
        selected_project_config = project / root.get("config", "vibeflow_project.jsonc")
        if selected_project_config != project / "vibeflow_project.jsonc" and selected_project_config.is_file():
            selected_document = dict(load_raw_config_document(selected_project_config).data)
            for removed in ("descriptors", "registry", "base_lib", "plugins"): selected_document.pop(removed, None)
            selected_project_config.write_text(json.dumps(selected_document))
        project_data = load_raw_config_document(project / "vibeflow_project.jsonc").data
        if project_data.get("project_target") == "javascript" and any(field in project_data for field in ("registry", "plugins")):
            continue
        inputs = resource_inputs(project)
        if not inputs:
            # An empty historical registration is still a real migrated root.
            if "descriptors" in project_data or "registry" in project_data:
                migrate_fixture(project)
            continue
        migrate_fixture(project)
        target = load_raw_config_document(project / "vibeflow_project.jsonc").data["project_target"]
        selections.append({"root":root["id"], "source":{"kind":"file", "ref":"code_plugin.py" if target == "python" else "code_plugin.ts", "export":"plugin"}})
        selection_targets[root["id"]] = target
        # Every fixture root gets its own package identity, just as production
        # plugins must have distinct identities when explicitly selected together.
        filename = project / selections[-1]["source"]["ref"]
        text = filename.read_text().replace("fixture.resources", "fixture." + root["id"])
        filename.write_text(text)
    for root in roots:
        if not isinstance(root, dict) or not root.get("path"):
            continue
        project = (workspace_path.parent / root["path"]).resolve()
        target = load_raw_config_document(project / "vibeflow_project.jsonc").data.get("project_target") if (project / "vibeflow_project.jsonc").is_file() else None
        for config in sorted(project.rglob("*.jsonc")) if project.is_dir() else ():
            try:
                raw_config = load_raw_config_document(config).data
            except ValueError:
                continue  # Syntax failures belong to the formal parser.
            if "pipeline" not in raw_config or not selections:
                continue
            data = dict(raw_config)
            existing = [item for item in data.get("plugins", []) if not isinstance(item, dict) or item.get("source", {}).get("ref") not in {"code_plugin.py", "code_plugin.ts"}]
            data["plugins"] = [item for item in selections if selection_targets[item["root"]] == target] + existing
            config.write_text(json.dumps(data, indent=2) + "\n")


def prepare_config_fixture(config_path):
    path = Path(config_path).resolve()
    parents = (path if path.is_dir() else path.parent, *path.parents)
    for parent in parents:
        workspace = parent / "vibeflow_config.jsonc"
        if workspace.is_file():
            prepare_workspace_fixture(workspace)
            return
    for parent in parents:
        if (parent / "vibeflow_project.jsonc").is_file() and resource_inputs(parent):
            migrate_fixture(parent)
            return


def publish_runtime_fixture(config_path, registry):
    """Publish a native-runtime test's fixed classes and selected SDK hooks."""
    from tests.fixtures.support.rule_inspection import write_registry_project
    config_path = Path(config_path)
    if not config_path.is_file():
        return
    data = dict(load_raw_config_document(config_path).data)
    selections = data.get("plugins", [])
    legacy = [item for item in selections if isinstance(item, dict) and ("module" in item or "class" in item)]
    base_specs = data.get("base_lib", {}).get("modules", [])
    legacy_base = [item for item in base_specs if isinstance(item, dict) and item.get("status", "implemented") == "implemented" and "module" in item]
    if not legacy and not legacy_base and any(isinstance(item, dict) and "source" in item for item in selections):
        return
    project = config_path.parent
    keys = set()
    def visit(body):
        for item in body.get("pipeline", body).get("nodes", []):
            if item.get("type_used") in registry.available():
                keys.add(item["type_used"])
        nested = body.get("nodesets", {})
        for definition in nested.values() if isinstance(nested, dict) else nested:
            visit(definition)
    visit(data)
    for spec in data.get("nodeset_imports", []):
        imported = (config_path.parent / spec["path"]).resolve()
        if imported.is_file():
            visit(dict(load_raw_config_document(imported).data))
    write_registry_project(project, registry, sorted(keys))
    migrate_fixture(project, configs=[config_path])
    data = dict(load_raw_config_document(config_path).data)
    selected = [item for item in data["plugins"] if isinstance(item, dict) and "source" in item]
    library_definitions = []
    for spec in legacy_base:
        module = spec["module"]
        path = project / (module.replace(".", "/") + ".py")
        text = path.read_text()
        lines = text.splitlines(keepends=True)
        for statement in ast.walk(ast.parse(text)):
            if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "BASE_LIB_INFO" for target in statement.targets):
                for line in range(statement.lineno - 1, statement.end_lineno):
                    lines[line] = "\n"
        path.write_text("".join(lines))
        library_definitions.append({"id": module, "source": {"kind": "file", "ref": path.relative_to(project).as_posix()},
            "rulesets": ["vibeflow.base_lib"], **{key: spec[key] for key in ("display_name", "description", "category", "version") if key in spec}})
    if library_definitions:
        code = "from vibeflow.targets.python.sdk import Plugin,base_lib\n\n"
        code += "plugin = Plugin(id='fixture.libraries', resources=[\n" + ",\n".join(f"    base_lib(**{item!r})" for item in library_definitions) + "\n])\n"
        (project / "selected_libraries.py").write_text(code)
        selected.append({"source": {"kind": "file", "ref": "selected_libraries.py"}})
        for spec in base_specs:
            if spec in legacy_base:
                spec.clear(); spec["id"] = library_definitions[legacy_base.index(spec)]["id"]
        data["base_lib"]["modules"] = [({"id": item["id"]} if "id" in item and "module" not in item else item) for item in base_specs]
    for index, spec in enumerate(legacy):
        implementation = Path(spec["module"])
        if not implementation.is_absolute():
            implementation = project / (str(implementation).replace(".", "/") + ".py")
        text = implementation.read_text()
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        info = None
        for statement in ast.walk(tree):
            if isinstance(statement, ast.Assign) and any(isinstance(target,ast.Name) and target.id == "PLUGIN_INFO" for target in statement.targets):
                if isinstance(statement.value,ast.Call):
                    try: info = [ast.literal_eval(arg) for arg in statement.value.args]
                    except (ValueError, TypeError): pass
                for line in range(statement.lineno - 1, statement.end_lineno): lines[line] = "\n"
        implementation.write_text("".join(lines))
        class_name = spec.get("class", "Plugin")
        plugin_id = spec.get("id", info[0] if info else implementation.stem)
        factory_module = implementation.relative_to(project).with_suffix("").as_posix().replace("/", ".")
        filename = f"selected_lifecycle_{index}.py"
        code = f'from vibeflow.targets.python.sdk import Plugin\n\ndef create(context):\n    from {factory_module} import {class_name}\n    instance = {class_name}()\n    instance.config = context["config"]\n    if hasattr(instance, "configure"):\n        instance.configure(context["config"])\n    return instance\n\n'
        code += f'plugin = Plugin(id={plugin_id!r}, {spec.get("type","runtime")}=create, display_name={spec.get("display_name",info[2] if info else plugin_id)!r}, description={spec.get("description",info[4] if info else plugin_id)!r}, version={spec.get("version",info[5] if info else "1.0")!r})\n'
        (project / filename).write_text(code)
        selected.append({"source":{"kind":"file","ref":filename},"config":spec.get("config", {})})
    planned = []
    for spec in selections:
        if isinstance(spec, dict) and spec.get("status") == "planned":
            item = dict(spec);item["id"] = item.pop("name", item.get("id", "future"));item.pop("category",None)
            planned.append(item)
    data["plugins"] = selected + planned
    config_path.write_text(json.dumps(data))
