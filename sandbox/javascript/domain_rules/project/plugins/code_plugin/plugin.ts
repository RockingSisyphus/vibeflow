import {definePlugin,defineNode,defineNodeType,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineResource} from "@vibeflow/plugin";
export const resource_0 = defineRule({"id": "example.model_definition", "display_name": "", "description": "modelForward belongs to model_block and each block defines one modelForward.", "implementations": [{"language": "typescript", "source": {"kind": "file", "ref": "rules/model_definition.ts", "export": "check"}}], "inputs": {}, "outputs": {}, "params_schema": {"model_tag": {"type": "string"}}, "params_defaults": {"model_tag": "model_block"}, "handler": "", "scope": "call", "level": "node"});

export const resource_1 = defineRule({"id": "example.model_files", "display_name": "", "description": "", "implementations": [{"language": "typescript", "source": {"kind": "file", "ref": "rules/model_files.ts", "export": "check"}}], "inputs": {}, "outputs": {}, "params_schema": {}, "params_defaults": {}, "handler": "", "scope": "call", "level": "graph"});

export const resource_2 = defineRuleset({"id": "example.model_domain", "calls": [{"id": "model_definition", "params": {}, "rule_id": "example.model_definition"}], "relations": [], "entrypoints": {"static": ["model_definition"], "run": ["model_definition"]}, "display_name": "", "description": "", "workflow_default": false, "graph_scope": null});

export const resource_3 = defineRuleset({"id": "example.model_layout", "calls": [{"id": "files", "params": {}, "rule_id": "example.model_files"}], "relations": [], "entrypoints": {"static": ["files"]}, "display_name": "", "description": "", "workflow_default": true, "graph_scope": null});

export const resource_4 = defineDataSchema({"type_key": "example.feature", "representation": "json", "display_name": "", "description": "", "schema": {"type": "number", "$schema": "https://json-schema.org/draft/2020-12/schema"}});

export const resource_5 = defineDataSchema({"type_key": "example.input", "representation": "json", "display_name": "", "description": "", "schema": {"type": "number", "$schema": "https://json-schema.org/draft/2020-12/schema"}});

export const resource_6 = defineDataSchema({"type_key": "example.output", "representation": "json", "display_name": "", "description": "", "schema": {"type": "number", "$schema": "https://json-schema.org/draft/2020-12/schema"}});

export const plugin = definePlugin({id:"example.javascript.domain_rules", resources:[resource_0, resource_1, resource_2, resource_3, resource_4, resource_5, resource_6]});
