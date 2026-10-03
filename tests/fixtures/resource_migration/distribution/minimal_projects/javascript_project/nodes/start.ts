import {defineNode} from "@vibeflow/plugin";
function run(): Readonly<Record<never, never>> {
  return {};
}

export const startNode=defineNode({...{"rulesets": ["vibeflow.process"], "type_key": "minimal.start", "display_name": "Workflow start", "description": "Marks the structural start of the minimal workflow.", "version": "0.15.0", "flow_kind": "terminal", "contract": {"requires": [], "provides": [], "params_schema": {}, "params_defaults": {}, "input_semantics": {}, "output_semantics": {}}, "base_libs": [], "capabilities": [], "tags": ["boundary"]},run});
