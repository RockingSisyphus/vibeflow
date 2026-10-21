"""Observe actual call/source Rules across multiple Node types in formal validate."""

import argparse
import json
from pathlib import Path

from tests.fixtures.python.sdk_defaults.validate_probe import execute, write_project


CHECKS = '''
from pathlib import Path
import json
from vibeflow.targets.python.sdk import rule, ruleset, RuleCall
from vibeflow.core.rules import RuleResult
seen = []
def record(context, kind):
    sources = context.facts["source_context"]
    assert len(sources.nodes) == 1
    assert sources.nodes[0].definition_id == context.subject["descriptor"].id
    assert "global_graph" not in context.facts
    seen.append((sources, context.subject["descriptor"], kind))
    Path(__file__).with_name("identity.json").write_text(json.dumps({
        "checks": len(seen), "sources": len({id(item[0]) for item in seen}),
        "descriptors": len({id(item[1]) for item in seen}),
        "call_checks": sum(item[2] == "call" for item in seen),
        "source_checks": sum(item[2] == "source" for item in seen),
    }))
    return RuleResult()
@rule(id="probe.identity.call", scope="call")
def call_check(context, inputs, params):
    assert context.facts["call"] is not None
    assert context.subject["rule_call_id"] == "call"
    return record(context, "call")
@rule(id="probe.identity.source", scope="source")
def source_check(context, inputs, params):
    assert "call" not in context.facts
    assert "workflow" not in context.scope
    assert "call_id" not in context.subject
    return record(context, "source")
identity = ruleset(id="probe.identity", calls=[
    RuleCall(id="call", rule_id="probe.identity.call"),
    RuleCall(id="source", rule_id="probe.identity.source"),
])
'''


def observe(work):
    root = work / "project"
    write_project(root, "integer", 1)
    path = root / "nodes/steps.py"
    code = path.read_text()
    start = code.index('@node(node_type="vibeflow.node",id="probe.defaults"')
    end = code.index('@node(node_type="vibeflow.node",id="probe.end"', start)
    template = code[start:end].replace('rulesets=["vibeflow.process"]', 'rulesets=["probe.identity"]')
    resources = []
    implementations = []
    for index in range(12):
        name = f"Defaults{index}"
        implementations.append(template.replace('probe.defaults', f'probe.defaults{index}').replace('class Defaults:', f'class {name}:').replace('"result"', f'"result{index}"'))
        resources.append(name)
    code = code[:start] + '\n'.join(implementations) + code[end:]
    path.write_text(code.replace('rulesets=["vibeflow.io"]', 'rulesets=[]'))
    plugin = root / "plugins/schemas/plugin.py"
    source = plugin.read_text()
    source = source.replace('plugin=Plugin(', CHECKS + '\nplugin=Plugin(').replace('resources=[inspection]', 'resources=[inspection,call_check,source_check,identity]')
    plugin.write_text(source)
    config = root / "workflow.jsonc"
    workflow = json.loads(config.read_text())
    original = workflow["pipeline"]["nodes"]
    repeated = [{**original[1], "id":f"inspect{i}", "definition_id":f"probe.defaults{i}"} for i in range(12)]
    workflow["pipeline"]["nodes"] = [original[0], *repeated, original[2]]
    ids = [item["id"] for item in workflow["pipeline"]["nodes"]]
    workflow["pipeline"]["edges"] = [ids[i:i+2] for i in range(len(ids)-1)]
    workflow["pipeline"]["outputs"] = []
    config.write_text(json.dumps(workflow))
    validation = execute(root, "validate", work)
    identity_path = root / "plugins/schemas/identity.json"
    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
    matched = validation["exit_code"] == 0 and identity == {
        "checks":24,"sources":12,"descriptors":12,"call_checks":12,"source_checks":12}
    return {"schema":"vibeflow.context-reuse-cli.v1", "matched":matched,
            "identity":identity, "validate":validation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    result = observe(args.work.resolve())
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({"matched":result["matched"],"identity":result["identity"],"exit":result["validate"]["exit_code"]}))
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
