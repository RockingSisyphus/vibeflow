"""Inspect the current workflow's fixed resource contributions without checks."""
import argparse
import json

from vibeflow.core.descriptors.contributions import RESOURCE_GROUPS
from vibeflow.tooling.project.descriptor_loader import load_workflow_plugins
from vibeflow.tooling.project.workspace_loader import load_project_workspace, load_workspace_config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibeflow inspect-resources")
    parser.add_argument("--config", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--kind", choices=tuple(RESOURCE_GROUPS))
    parser.add_argument("--id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        workspace = load_workspace_config(args.workspace) if args.workspace else load_project_workspace(args.config)
        loaded = load_workflow_plugins(workspace, args.config)
        resources = []
        for kind, group in RESOURCE_GROUPS.items():
            if args.kind and kind != args.kind:
                continue
            for descriptor in getattr(loaded.catalogs, group):
                if args.id and descriptor.id != args.id:
                    continue
                resources.append({"descriptor": descriptor.to_dict(), "origin": loaded.catalogs.origins[(group,descriptor.id)].to_dict()})
        payload = {"status":"PASS", "resources":resources}
    except Exception as error:
        payload = {"status":"ERROR", "code":getattr(error,"code",getattr(error,"rule_id","PLUGIN.DECLARATION.LOAD")), "error":str(error), "diagnostics":list(getattr(error,"diagnostics",()))}
    if args.json:
        print(json.dumps(payload,ensure_ascii=False))
    else:
        for item in payload.get("resources",[]):
            descriptor = item["descriptor"]
            print(f'{descriptor["kind"]} {descriptor.get("id",descriptor.get("type_key"))}: {item["origin"]["plugin_id"]}')
        if payload["status"] == "ERROR": print(f'{payload["code"]}: {payload["error"]}')
    return int(payload["status"] == "ERROR")
