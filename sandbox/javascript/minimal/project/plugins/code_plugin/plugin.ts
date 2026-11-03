import {definePlugin,defineRuleset,defineDataSchema,defineBaseLib} from "@vibeflow/plugin";






export const resource_4=defineDataSchema({"type_key": "greeting.text", "representation": "json", "schema": {"type": "string"}});

export const resource_5=defineDataSchema({"type_key": "name.text", "representation": "json", "schema": {"type": "string", "minLength": 1}});



export const resource_1000 = defineDataSchema({"type_key":"app.session","schema":{}});
export const plugin=definePlugin({id:"example.javascript.minimal",resources:[resource_1000,resource_4,resource_5]});
