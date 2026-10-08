import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension,defineResource} from "@vibeflow/plugin";
export const resource_0 = defineNode({"type_key": "example.model", "display_name": "Model", "description": "One explicitly named function block.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "example.input", "cardinality": "exactly_one", "display_name": "example.input"}], "provides": [{"key": "feature", "type": "example.feature", "display_name": "feature"}], "input_semantics": {"example.input": ["Numerical input to this functional block."]}, "output_semantics": {"feature": ["Numerical output produced by this functional block."]}}, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "nodes/model.ts", "export": "run"}}], "rulesets": ["vibeflow.process", "example.model_domain"], "presentation": {"fill": "#cceeff", "shape": "rect"}, "tags": ["model_block"]});

export const resource_1 = defineNode({"type_key": "example.transform", "display_name": "Transform", "description": "One explicitly named function block.", "version": "0.15.0", "flow_kind": "process", "contract": {"requires": [{"type": "example.feature", "cardinality": "exactly_one", "display_name": "example.feature"}], "provides": [{"key": "output", "type": "example.output", "display_name": "output"}], "input_semantics": {"example.feature": ["Numerical input to this functional block."]}, "output_semantics": {"output": ["Numerical output produced by this functional block."]}}, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "nodes/transform.ts", "export": "run"}}], "rulesets": ["vibeflow.process", "example.model_domain"], "presentation": {"fill": "#dff7df", "shape": "rounded"}, "tags": ["data_transform"]});

export const resource_2 = defineNode({"type_key": "example.boundary", "display_name": "Workflow boundary", "description": "A native terminal boundary around the example graph.", "version": "0.15.0", "flow_kind": "terminal", "rulesets": ["vibeflow.io"], "contract": {"requires": [], "provides": []}, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "nodes/boundary.ts", "export": "run"}}], "tags": ["boundary"]});

export const resource_3 = defineRule({"id": "example.model_definition", "description": "modelForward belongs to model_block and each block defines one modelForward.", "implementations": [{"language": "typescript", "source": {"kind": "file", "ref": "rules/model_definition.ts", "export": "check"}}], "params_schema": {"model_tag": {"type": "string"}}, "params_defaults": {"model_tag": "model_block"}});

export const resource_4 = defineRuleset({"id": "example.model_domain", "calls": [{"id": "model_definition", "rule_id": "example.model_definition"}], "entrypoints": {"static": ["model_definition"], "run": ["model_definition"]}});

export const resource_5 = defineDataSchema({"type_key": "example.feature", "representation": "json", "schema": {"type": "number"}});

export const resource_6 = defineDataSchema({"type_key": "example.input", "representation": "json", "schema": {"type": "number"}});

export const resource_7 = defineDataSchema({"type_key": "example.output", "representation": "json", "schema": {"type": "number"}});

export const plugin = definePlugin({id:"fixture.resources", resources:[resource_0, resource_1, resource_2, resource_3, resource_4, resource_5, resource_6, resource_7]});
