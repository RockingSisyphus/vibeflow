import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineResource} from "@vibeflow/plugin";

































export const resource_45 = defineDataSchema({"type_key": "sandbox.addend", "representation": "json", "schema": {"type": "number"}});
export const resource_46 = defineDataSchema({"type_key": "sandbox.async.value", "representation": "json", "schema": {"type": "number"}});
export const resource_49 = defineDataSchema({"type_key": "sandbox.branch.forwarded", "representation": "json", "schema": {"type": "number"}});
export const resource_50 = defineDataSchema({"type_key": "sandbox.branch.message", "representation": "json", "schema": {"type": "string", "minLength": 1}});
export const resource_51 = defineDataSchema({"type_key": "sandbox.branch.output", "representation": "json", "schema": {"type": "string", "minLength": 1}});
export const resource_52 = defineDataSchema({"type_key": "sandbox.branch.positive", "representation": "json", "schema": {"type": "boolean"}});
export const resource_53 = defineDataSchema({"type_key": "sandbox.fanout.added.output", "representation": "json", "schema": {"type": "number"}});
export const resource_54 = defineDataSchema({"type_key": "sandbox.fanout.added", "representation": "json", "schema": {"type": "number"}});
export const resource_55 = defineDataSchema({"type_key": "sandbox.fanout.subtracted.output", "representation": "json", "schema": {"type": "number"}});
export const resource_56 = defineDataSchema({"type_key": "sandbox.fanout.subtracted", "representation": "json", "schema": {"type": "number"}});
export const resource_57 = defineDataSchema({"type_key": "sandbox.loop.done", "representation": "json", "schema": {"type": "boolean"}});
export const resource_58 = defineDataSchema({"type_key": "sandbox.loop.history", "representation": "json", "schema": {"type": "array", "items": {"type": "number"}}});
export const resource_59 = defineDataSchema({"type_key": "sandbox.loop.iterations", "representation": "json", "schema": {"type": "integer", "minimum": 0}});
export const resource_60 = defineDataSchema({"type_key": "sandbox.loop.next", "representation": "json", "schema": {"type": "number"}});
export const resource_61 = defineDataSchema({"type_key": "sandbox.loop.result", "representation": "json", "schema": {"type": "number"}});
export const resource_62 = defineDataSchema({"type_key": "sandbox.loop.value", "representation": "json", "schema": {"type": "number"}});
export const resource_63 = defineDataSchema({"type_key": "sandbox.math.result", "representation": "json", "schema": {"type": "number"}});
export const resource_64 = defineDataSchema({"type_key": "sandbox.number", "representation": "json", "schema": {"type": "number"}});
export const resource_65 = defineDataSchema({"type_key": "sandbox.optional.offset", "representation": "json", "schema": {"type": "number"}});
export const resource_66 = defineDataSchema({"type_key": "sandbox.override.default", "representation": "json", "schema": {"type": "number"}});
export const resource_67 = defineDataSchema({"type_key": "sandbox.override.joined", "representation": "json", "schema": {"type": "number"}});
export const resource_68 = defineDataSchema({"type_key": "sandbox.storage.key", "representation": "json", "schema": {"type": "string", "minLength": 1}});
export const resource_71 = defineDataSchema({"type_key": "sandbox.storage.value", "representation": "json", "schema": {"type": "string"}});
export const resource_72 = defineDataSchema({"type_key": "sandbox.subtrahend.forwarded", "representation": "json", "schema": {"type": "number"}});
export const resource_73 = defineDataSchema({"type_key": "sandbox.subtrahend", "representation": "json", "schema": {"type": "number"}});
export const resource_74 = defineDataSchema({"type_key": "sandbox.sum", "representation": "json", "schema": {"type": "number"}});
export const resource_75 = defineDataSchema({"type_key": "sandbox.x", "representation": "json", "schema": {"type": "number"}});

export const resource_1000 = defineDataSchema({"type_key":"app.session","schema":{}});
export const plugin = definePlugin({id:"workflow.math",resources:[resource_1000, resource_45, resource_46,   resource_49, resource_50, resource_51, resource_52, resource_53, resource_54, resource_55, resource_56, resource_57, resource_58, resource_59, resource_60, resource_61, resource_62, resource_63, resource_64, resource_65, resource_66, resource_67, resource_68,   resource_71, resource_72, resource_73, resource_74, resource_75]});
