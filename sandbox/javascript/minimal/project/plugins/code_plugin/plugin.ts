import {definePlugin,defineRuleset,defineDataSchema,defineBaseLib,defineCapability} from "@vibeflow/plugin";


export const resource_1=defineCapability({"id": "example.clock", "targets": ["browser", "node"], "operations": {"now": {"input_type": "clock.now.request", "output_type": "clock.now.result", "completion": "suspend"}}});

export const resource_2=defineDataSchema({"type_key": "clock.now.request", "representation": "json", "schema": {"type": "null"}});

export const resource_3=defineDataSchema({"type_key": "clock.now.result", "representation": "json", "schema": {"type": "integer"}});

export const resource_4=defineDataSchema({"type_key": "greeting.text", "representation": "json", "schema": {"type": "string"}});

export const resource_5=defineDataSchema({"type_key": "name.text", "representation": "json", "schema": {"type": "string", "minLength": 1}});



export const plugin=definePlugin({id:"example.javascript.minimal",resources:[resource_1,resource_2,resource_3,resource_4,resource_5]});
