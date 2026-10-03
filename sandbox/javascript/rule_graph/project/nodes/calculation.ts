import {defineNode} from "@vibeflow/plugin";
export function boundary(inputs, params) { return {}; }
export function calculate(inputs, params) {
  return {result: inputs["example.input"].value * 2 + 1};
}

export const resource_0Definition=defineNode({...{"type_key": "example.boundary", "display_name": "Boundary", "description": "An executable Node in the typed Rule graph example.", "version": "0.15.0", "flow_kind": "terminal", "contract": {}, "rulesets": [], "tags": ["rule_graph"], "targets": ["browser", "node"]},run:boundary});

export const resource_1Definition=defineNode({...{"type_key": "example.calculate", "display_name": "Calculate", "description": "An executable Node in the typed Rule graph example.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "example.input", "cardinality": "exactly_one", "display_name": "Input"}], "provides": [{"key": "result", "type": "example.output", "display_name": "Result"}], "input_semantics": {"example.input": ["The number to calculate."]}, "output_semantics": {"result": ["Twice the number plus one."]}}, "rulesets": ["example.rule_graph"], "tags": ["rule_graph"], "targets": ["browser", "node"]},run:calculate});
