"""Exercise resource Rules with actual portable facts and Target import parsing."""
from types import SimpleNamespace
from pathlib import Path
from vibeflow.core.descriptors.resource_use import ResourceUse, RESOURCE_USE_TYPE
from vibeflow.core.rules import RuleRecord
from vibeflow.targets.shared.rule_support.resource_use.references import references

def owner(kind, identifier, path, *, role='entry', libraries=(), plugin='', lines=None):
    return {'kind': kind, 'id': identifier, 'path': path, 'role': role, 'base_libs': libraries,
            'dependencies': (), 'plugin_id': plugin, 'import_lines': lines, 'symbol': ''}


def check(owners, *, source='entry.py', target='helper.py', more_scopes=()):
    scopes = ({'id': 'selected', 'owners': owners}, *more_scopes)
    workflows = [dict(workflow=scope['id'], path='config.jsonc', owners=scope['owners'], resources=[],
        entry_resources=[(item['kind'],item['id']) for item in scope['owners'] if item['path']==source],
        imports=[dict(path=source,target=target,line=1)]) for scope in scopes]
    context = SimpleNamespace(facts={'root':{'resource_workflows':workflows}}, scope={'level':'root'}, subject={'id':'root'})
    record = RuleRecord(RESOURCE_USE_TYPE, {'workflows':{scope['id']:ResourceUse(scope['id']).to_dict() for scope in scopes}})
    return references(context, {'use':record}, {}).findings



def javascript_references(project, policy):
    from vibeflow.targets.javascript.build.resource_facts import resource_import_facts
    owners = tuple({**item, "symbol":item.get("export", ""), "role":item.get("role","entry"),
        "base_libs":policy.get("nodeBaseLibs",policy.get("node_base_libs",{})).get(item["id"],()),
        "dependencies":policy.get("baseLibDependencies",policy.get("base_lib_dependencies",{})).get(item["id"],())}
        for item in policy["owners"])
    root = SimpleNamespace(path=Path(project), project_config={})
    facts = resource_import_facts(SimpleNamespace(root=Path(project).parent), root,
        SimpleNamespace(packages=()), owners, syntax_cache={}, node_command="node")
    workflow = {**facts,"workflow":"test:main.jsonc", "path":"main.jsonc", "resources":[],
        "entry_resources":[(item["kind"],item["id"]) for item in owners if item["kind"]=="node"]}
    context = SimpleNamespace(facts={"root":{"resource_workflows":[workflow]}},scope={"level":"root"},subject={"id":"test"})
    record = RuleRecord(RESOURCE_USE_TYPE,{"workflows":{workflow["workflow"]:ResourceUse(workflow["workflow"]).to_dict()}})
    return tuple({"code":item.rule_id,"message":item.message,"severity":item.severity,
        "file":item.source_location["path"],"line":item.source_location["line"],"column":item.source_location["column"],
        "owner":{"id":item.details["resource_id"],"kind":item.details["resource_kind"],"path":item.source_location["path"]}}
        for item in references(context,{"use":record},{}).findings)
