import {definePlugin,defineDataSchema} from "@vibeflow/plugin";
const r14=defineDataSchema({"type_key": "scenario", "representation": "json", "schema": {"type": "string"}});
const r15=defineDataSchema({"type_key": "receipt", "representation": "json", "schema": {"type": "integer"}});
const r16=defineDataSchema({"type_key": "report", "representation": "json", "schema": {"type": "array", "items": {"type": "integer"}}});
export const plugin=definePlugin({id:"graph.concurrency",resources:[r14,r15,r16]});
