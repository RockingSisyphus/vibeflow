import {definePlugin,defineDataSchema} from "@vibeflow/plugin";
const schema0=defineDataSchema({"type_key": "payload.internal", "representation": "json", "schema": {}});
const schema1=defineDataSchema({"type_key": "payload.processed", "representation": "json", "schema": {}});
const schema2=defineDataSchema({"type_key": "payload.request", "representation": "json", "schema": {}});
const schema3=defineDataSchema({"type_key": "payload.response", "representation": "json", "schema": {}});
export const plugin=definePlugin({id:"minimal.javascript",resources:[schema0,schema1,schema2,schema3]});
