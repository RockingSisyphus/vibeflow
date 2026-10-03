import {defineNode} from "@vibeflow/plugin";
type Envelope = Readonly<{value: number}>;
export function run(inputs: Readonly<{"example.feature": Envelope}>) {
  return {output: inputs["example.feature"].value + 1};
}

export const resource_2Definition=defineNode({...{"type_key": "example.transform", "display_name": "Transform", "description": "One explicitly named function block.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "example.feature", "cardinality": "exactly_one", "display_name": "example.feature"}], "provides": [{"key": "output", "type": "example.output", "display_name": "output"}], "input_semantics": {"example.feature": ["Numerical input to this functional block."]}, "output_semantics": {"output": ["Numerical output produced by this functional block."]}}, "rulesets": ["vibeflow.process", "example.model_domain"], "presentation": {"fill": "#dff7df", "shape": "rounded"}, "tags": ["data_transform"], "targets": ["browser", "node"]},run:run});
