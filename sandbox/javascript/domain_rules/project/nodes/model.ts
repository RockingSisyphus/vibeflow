import {defineNode} from "@vibeflow/plugin";
type Envelope = Readonly<{value: number}>;
export function modelForward(value: number): number { return value * 2; }
export function run(inputs: Readonly<{"example.input": Envelope}>) {
  return {feature: modelForward(inputs["example.input"].value)};
}

export const resource_1Definition=defineNode({...{"type_key": "example.model", "display_name": "Model", "description": "One explicitly named function block.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "example.input", "cardinality": "exactly_one", "display_name": "example.input"}], "provides": [{"key": "feature", "type": "example.feature", "display_name": "feature"}], "input_semantics": {"example.input": ["Numerical input to this functional block."]}, "output_semantics": {"feature": ["Numerical output produced by this functional block."]}}, "rulesets": ["vibeflow.process", "example.model_domain"], "presentation": {"fill": "#cceeff", "shape": "rect"}, "tags": ["model_block"], "targets": ["browser", "node"]},run:run});
