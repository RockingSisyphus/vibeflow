import {defineNode} from "@vibeflow/plugin";
function run(): Readonly<Record<never, never>> {
  return {};
}

export const endNode=defineNode({node_type:"vibeflow.node",...{"rulesets": ["vibeflow.process"], "id": "minimal.end", "display_name": "Workflow end", "description": "Marks the structural end after the response is available.", "version": "0.15.0", "flow_kind": "terminal", "contract": {"requires": [], "provides": [], "params_schema": {}, "params_defaults": {}, "input_semantics": {}, "output_semantics": {}}, "base_libs": [], "capabilities": [], "tags": ["boundary"]},run});
