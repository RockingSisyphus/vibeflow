import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension,defineResource} from "@vibeflow/plugin";
export const resource_0 = defineBaseLib({"id": "example.text", "display_name": "Text helpers", "description": "Pure text normalization helpers.", "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "base_lib/text.ts"}}], "dependencies": [], "external_packages": [], "rulesets": ["vibeflow.base_lib"]});

export const resource_1 = defineCapability({"id": "example.clock", "targets": ["browser", "node"], "operations": {"now": {"input_type": "clock.now.request", "output_type": "clock.now.result", "completion": "suspend"}}});

export const resource_2 = defineDataSchema({"type_key": "clock.now.request", "representation": "json", "schema": {"type": "null"}});

export const resource_3 = defineDataSchema({"type_key": "clock.now.result", "representation": "json", "schema": {"type": "integer"}});

export const resource_4 = defineDataSchema({"type_key": "greeting.text", "representation": "json", "schema": {"type": "string"}});

export const resource_5 = defineDataSchema({"type_key": "name.text", "representation": "json", "schema": {"type": "string", "minLength": 1}});

export const resource_6 = defineNode({"rulesets": ["vibeflow.process"], "type_key": "example.greet", "display_name": "Build greeting", "description": "Builds a greeting from a name and an injected clock.", "version": "1.0.0", "flow_kind": "terminal", "contract": {"requires": [{"type": "name.text", "cardinality": "exactly_one", "display_name": "Name"}], "provides": [{"key": "greeting", "type": "greeting.text", "display_name": "Greeting"}], "params_schema": {"prefix": {"type": "string"}}, "params_defaults": {"prefix": "Hello"}, "input_semantics": {"name.text": ["Name input consumed by this node."]}, "output_semantics": {"greeting": ["Greeting output produced by this node."]}}, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "completion": "suspend", "source": {"kind": "file", "ref": "nodes/greet.ts", "export": "run"}}], "base_libs": ["example.text"], "capabilities": [{"id": "example.clock", "operations": ["now"]}], "tags": ["example"]});

export const plugin = definePlugin({id:"fixture.resources", resources:[resource_0, resource_1, resource_2, resource_3, resource_4, resource_5, resource_6]});
