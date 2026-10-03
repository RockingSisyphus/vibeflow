import {defineNode} from "@vibeflow/plugin";
export function run() { return {}; }

export const resource_0Definition=defineNode({...{"type_key": "example.boundary", "display_name": "Workflow boundary", "description": "A native terminal boundary around the example graph.", "version": "0.15.0", "flow_kind": "terminal", "rulesets": ["vibeflow.io"], "contract": {"requires": [], "provides": []}, "tags": ["boundary"], "targets": ["browser", "node"]},run:run});
