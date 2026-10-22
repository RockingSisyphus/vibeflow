"""Operation-local project inventory, resource preparation and governance assembly."""

from dataclasses import dataclass, replace
from pathlib import Path
from os.path import relpath
from vibeflow.tooling.project.resource_facts import implementation_paths

from vibeflow.core.descriptors.contributions import resource_kind
from vibeflow.core.findings import HealthFinding
from vibeflow.tooling.project.inventory import InventoryIssue, inventory_project
from vibeflow.tooling.project.governance import load_governance_config, governance_context, execute_governance
from vibeflow.tooling.project.resources import prepare_workflow_resources, prepare_governance_resources


@dataclass(frozen=True)
class GovernanceReview:
    inventory: object
    resources: tuple
    results: tuple
    findings: tuple
    architecture_path: Path | None = None


class ProjectPreparation:
    """One command owns this state; it is neither a runtime nor a global cache."""

    def __init__(self, workspace, *, root=None, workflow=None, node_command="node", includes=()):
        self.workspace, self.root, self.node_command = workspace, root, node_command
        self.includes, self.usage_complete = includes, root is None and workflow is None
        self.inventory = inventory_project(workspace, root_ids={root.id} if root else None)
        if workflow is not None:
            selected = Path(workflow).resolve()
            self.inventory = replace(self.inventory,
                workflows=tuple(item for item in self.inventory.workflows if item.path == selected),
                issues=tuple(item for item in self.inventory.issues if item.path == selected))
        self.declarations = {}
        self.binding_contexts = {}
        self.syntax_caches = {}
        self.workflows = {}
        self.reviews = {}
        self.root_source_facts = {}
        self.root_private_imports = {}
        self._architecture_inputs = None

    def workflow_resources(self, path):
        path = Path(path).resolve()
        if path not in self.workflows:
            self.workflows[path] = prepare_workflow_resources(self.workspace, path, node_command=self.node_command, discovery_cache=self.declarations, syntax_caches=self.syntax_caches, binding_contexts=self.binding_contexts)
        return self.workflows[path]

    def resource_use(self, workflow_path):
        self.workflow_resources(workflow_path)
        self.review()
        use = self.workflow_resources(workflow_path).resource_use
        if use is None:
            raise ValueError("resource-use Rules did not produce an available result; inspect review findings")
        return use

    def review_graph(self, workflow_path, graph):
        """Re-evaluate the selected Rules when compiler hooks change references."""
        path = Path(workflow_path).resolve()
        prepared = self.workflow_resources(path)
        if prepared.graph is not graph:
            self.workflows[path] = replace(prepared, graph=graph, resource_use=None)
            self.reviews.clear()
        review = self.review()
        from vibeflow.tooling.project.resources.use_facts import workflow_identity
        identity = workflow_identity(self.workspace, path)
        return replace(review, findings=tuple(finding for finding in review.findings
            if not finding.details.get("workflow") or finding.details["workflow"] == identity))

    def review(self, *, write_architecture=False):
        if write_architecture in self.reviews:
            return self.reviews[write_architecture]
        issues = list(self.inventory.issues)
        for document in self.inventory.workflows:
            try:
                self.workflow_resources(document.path)
            except (OSError, ValueError, ImportError, SyntaxError) as error:
                issues.append(InventoryIssue(document.root_id, document.path,
                    (getattr(error, "code", "") or getattr(error, "rule_id", "") or "PROJECT.RESOURCE.PREPARATION"), str(error)))
        inventories = []
        roots = (self.root,) if self.root else self.workspace.roots
        for root in roots:
            if self.inventory.for_root(root.id):
                continue
            from vibeflow.tooling.project.resources.ownership import standalone_resources
            try:
                _, _, entries, _ = standalone_resources(self.workspace, root, (), node_ids=frozenset(),
                    node_command=self.node_command, discovery_cache=self.declarations)
                inventories.extend(entries)
            except (OSError, ValueError, ImportError, SyntaxError) as error:
                issues.append(InventoryIssue(root.id, root.path,
                    getattr(error, "code", "PROJECT.RESOURCE.PREPARATION"), str(error)))
        inventory = replace(self.inventory, issues=tuple(issues))
        roots = (self.root,) if self.root else self.workspace.roots
        configs = [(None, load_governance_config(self.workspace.root, "project"))]
        configs.extend((root, load_governance_config(root.path, "root")) for root in roots)
        governance = [(root, config, prepare_governance_resources(self.workspace, config,
            root=root, node_command=self.node_command, syntax_caches=self.syntax_caches, binding_contexts=self.binding_contexts)) for root, config in configs]
        resources = resource_usage(self.workspace, self.workflows, governance, inventories=inventories)
        results = []
        from vibeflow.tooling.project.rule_bindings import governance_rule_handlers
        for root, config, prepared in governance:
            scoped = resources if root is None else tuple(row for row in resources
                if row["owner"]["kind"] == "project" or row["owner"]["id"] == root.id)
            context = governance_context(inventory, root=root, resources=scoped)
            from vibeflow.tooling.project.resource_facts import governance_resource_facts
            level = "root" if root is not None else "project"
            extra = governance_resource_facts(self.workspace, self.workflows, governance, scoped,
                root=root, includes=self.includes)
            if root is None:
                shared = {}
                if config.selections:
                    for owner in roots:
                        from vibeflow.tooling.application.project_targets import preparation_adapter
                        imports = preparation_adapter(owner.project_target).shared_imports(self.workspace, owner,
                            node_command=self.node_command, syntax_cache=self.syntax_caches.setdefault(owner.project_target, {}))
                        for item in imports:
                            if item.get("shared"):
                                shared[(item["path"], item["imported_path"], item["line"])] = item
                extra.update(shared_imports=tuple(shared.values()), usage_complete=self.usage_complete)
            context = replace(context, facts={level: {**context.facts[level], **extra}})
            if root is not None and config.selections:
                from vibeflow.tooling.project.resources.use import resource_workflows
                context = replace(context, facts={"root": {**context.facts["root"],
                    "resource_workflows": resource_workflows(self, root),
                    "source_quality": self.source_facts(root),
                    "private_root_imports":self.root_private_imports[root.id]}})
            with governance_rule_handlers(prepared.catalogs, target_root=root or self.workspace.root,
                                          node_command=self.node_command) as handlers:
                results.extend(execute_governance(config, context, catalogs=prepared.catalogs, handlers=handlers))
        findings = tuple(HealthFinding(rule_id=item.code, severity="error", object_type="workflow",
            object_id=str(item.path), message=item.message, source_location={"path": str(item.path)},
            failure_layer="source", root_id=item.root_id) for item in issues)
        findings += tuple(finding for result in results for item in result.results.values() for finding in item.findings)
        from vibeflow.tooling.project.resources.use import collect_resource_uses
        findings += collect_resource_uses(self, results)
        architecture_path = None
        if write_architecture:
            if self.root is not None:
                raise ValueError("a root-scoped preparation cannot overwrite the project architecture")
            project_config = configs[0][1]
            purposes = project_config.rule_params.get("vibeflow.project.layout", {}).get("directories", ())
            self._architecture_inputs = (inventory, dict(resources=resources, workflows=self.workflows, directory_purposes=purposes))
            architecture_path = self.publish_architecture()
        review = GovernanceReview(inventory, resources, tuple(results), findings, architecture_path)
        self.reviews[write_architecture] = review
        return review

    def publish_architecture(self):
        """Refresh document existence after publication using the same prepared facts."""
        from vibeflow.tooling.architecture.project import write_project_architecture
        if self._architecture_inputs is None:
            return self.review(write_architecture=True).architecture_path
        inventory, facts = self._architecture_inputs
        return write_project_architecture(inventory, **facts)

    def source_facts(self, root):
        if root.id not in self.root_source_facts:
            from vibeflow.tooling.application.project_targets import preparation_adapter
            facts,imports = preparation_adapter(root.project_target).source_analysis(self.workspace,root,self.workflows,
                node_command=self.node_command,syntax_cache=self.syntax_caches.setdefault(root.project_target,{}))
            self.root_private_imports[root.id] = imports
            self.root_source_facts[root.id] = facts
        return self.root_source_facts[root.id]


def resource_usage(workspace, workflows, governance=(), *, inventories=()):
    """Count explicit declarations/dependencies by distinct consuming roots."""
    rows = {}

    def add(entry):
        descriptor, origin = entry.descriptor, entry.origin
        kind = resource_kind(descriptor)
        key = (origin.owner.kind, origin.owner.id, kind, descriptor.id, origin.path)
        path = Path(origin.path)
        base = Path(origin.owner.path)
        rows.setdefault(key, {"kind": kind, "id": descriptor.id, "owner": origin.owner.to_dict(),
            "path": str(path), "relative_path": Path(relpath(path, base)).as_posix(),
            "implementation_paths": implementation_paths(descriptor), "used_by_roots": set(), "used_by_workflows": []})
        return rows[key]

    for entry in inventories:
        add(entry)
    # Unselected shared packages are still shared resources, with zero consumers.
    packages = workspace.root / "plugins"
    for path in sorted(packages.iterdir()) if packages.is_dir() and workspace.root_for_path(workspace.root) is None else ():
        if not path.is_dir() or path.name.startswith((".", "__")):
            continue
        key = ("package", str(path.resolve()))
        rows[key] = {"kind":"plugin_declaration", "id":path.name,
            "owner":{"kind":"project", "id":"project", "path":str(workspace.root), "root_id":""},
            "path":str(path), "relative_path":path.relative_to(workspace.root).as_posix(),
            "used_by_roots":set(), "used_by_workflows":[], "governance":False}
    for workflow_path, prepared in workflows.items():
        root = workspace.root_for_path(workflow_path)
        from vibeflow.core.rules.planning import graph_rule_subjects
        references = {}
        for subject in graph_rule_subjects(prepared.graph):
            for node in subject.graph.nodes:
                references.setdefault(node.definition_id, set()).add(node.status)
        libraries = set()
        for node in prepared.catalogs.nodes:
            libraries.update(node.base_libs)
        for record in prepared.records:
            libraries.update(record.get("declaration", {}).get("base_libs", ()))
        pending = list(libraries)
        while pending:
            descriptor = prepared.catalogs.base_libs.get(pending.pop())
            for dependency in getattr(descriptor, "dependencies", ()):
                if dependency not in libraries:
                    libraries.add(dependency)
                    pending.append(dependency)
        for entry in prepared.resource_inventory:
            row = add(entry)
            if row["kind"] == "node" and prepared.catalogs.nodes.get(row["id"]) or row["kind"] == "base_lib" and row["id"] in libraries:
                row["used_by_roots"].add(root.id)
                row["used_by_workflows"].append({"path":Path(relpath(workflow_path, workspace.root)).as_posix(),
                    "root":root.id, "statuses":sorted(references.get(row["id"], {"implemented"})),
                    "relation":"declaration" if row["kind"] == "node" else "dependency"})
    workflow_packages={record["package_path"] for prepared in workflows.values() for record in prepared.records if record.get("status")!="planned"}
    for root, level, prepared in (
        *((workspace.root_for_path(path), path, value) for path, value in workflows.items()),
        *((root, config.level, value) for root, config, value in governance),
    ):
        for record in prepared.records:
            if record.get("status") == "planned":
                continue
            project = record.get("scope") == "project"
            key = ("package", record["package_path"])
            owner = {"kind": "project" if project else "root", "id": "project" if project else root.id, "path": str(workspace.root if project else root.path),
                     "root_id": "" if project else root.id}
            row = rows.setdefault(key, {"kind": "plugin_declaration", "id": record["id"], "owner": owner,
                "path": record["package_path"], "relative_path": (Path(record["package_path"]).relative_to(Path(owner["path"])).as_posix()
                    if Path(record["package_path"]).is_relative_to(owner["path"]) else record["source"]["ref"]),
                "used_by_roots": set(), "used_by_workflows": [], "governance": False})
            row["id"] = record["id"]
            own_rules = [rule for rule in prepared.catalogs.rules
                if prepared.catalogs.origins[("rules",rule.id)].owner.plugin_id == record["id"]]
            business = any(prepared.catalogs.origins[(group,item.id)].owner.plugin_id == record["id"]
                for group in ("node_types", "plugins") for item in getattr(prepared.catalogs, group))
            if level in {"root", "project"} and not business:
                from vibeflow.core.rules import compile_ruleset, RuleGraphError
                levels = {rule.level for rule in own_rules}
                for ruleset in prepared.catalogs.rulesets:
                    if prepared.catalogs.origins[("rulesets",ruleset.id)].owner.plugin_id != record["id"]:
                        continue
                    try:
                        levels.update(call.rule.level for call in compile_ruleset(ruleset,
                            rules=prepared.catalogs.rules, rulesets=prepared.catalogs.rulesets).invocations)
                    except RuleGraphError:
                        levels.add("unresolved")
                row["governance"] = record["package_path"] not in workflow_packages and bool(levels) and levels <= {"root", "project"}
            if root is not None:
                row["used_by_roots"].add(root.id)
            if isinstance(level, Path):
                row["used_by_workflows"].append({"path":Path(relpath(level, workspace.root)).as_posix(),
                    "root":root.id, "statuses":["implemented"], "relation":"selection"})
    return tuple({**row, "used_by_roots": sorted(row["used_by_roots"])} for _, row in sorted(rows.items(), key=lambda item: str(item[0])))
