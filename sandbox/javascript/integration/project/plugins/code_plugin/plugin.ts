import {portCapability,portSchema0,portSchema1,portSchema2,portSchema3} from "./port_resources";
import {definePlugin,defineNode,defineNodeType,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineResource} from "@vibeflow/plugin";


























































































export const resource_45 = defineDataSchema({"type_key": "sandbox.addend", "representation": "json", "schema": {"type": "number"}});

export const resource_46 = defineDataSchema({"type_key": "sandbox.async.value", "representation": "json", "schema": {"type": "number"}});

export const resource_47 = defineDataSchema({"type_key": "sandbox.audit.request", "representation": "json", "display_name": "Audit request", "description": "A generic detached-task audit request.", "schema": {"type": "object", "properties": {"label": {"type": "string", "minLength": 1}}, "required": ["label"], "additionalProperties": false}});

export const resource_48 = defineDataSchema({"type_key": "sandbox.audit.result", "representation": "json", "display_name": "Audit result", "description": "Acknowledgement returned by a generic audit host.", "schema": {"type": "object", "properties": {"accepted": {"type": "boolean"}}, "required": ["accepted"], "additionalProperties": false}});

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

export const resource_69 = defineDataSchema({"type_key": "sandbox.storage.read.request", "representation": "json", "schema": {"type": "object", "properties": {"key": {"type": "string", "minLength": 1}}, "required": ["key"], "additionalProperties": false}});

export const resource_70 = defineDataSchema({"type_key": "sandbox.storage.read.result", "representation": "json", "schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": false}});

export const resource_71 = defineDataSchema({"type_key": "sandbox.storage.value", "representation": "json", "schema": {"type": "string"}});

export const resource_72 = defineDataSchema({"type_key": "sandbox.subtrahend.forwarded", "representation": "json", "schema": {"type": "number"}});

export const resource_73 = defineDataSchema({"type_key": "sandbox.subtrahend", "representation": "json", "schema": {"type": "number"}});

export const resource_74 = defineDataSchema({"type_key": "sandbox.sum", "representation": "json", "schema": {"type": "number"}});

export const resource_75 = defineDataSchema({"type_key": "sandbox.x", "representation": "json", "schema": {"type": "number"}});

export const resource_76 = defineCapability({"id": "sandbox.audit", "targets": ["browser", "node"], "display_name": "Audit sink", "description": "A host-supplied generic sink used to observe detached cleanup.", "operations": {"record": {"input_type": "sandbox.audit.request", "output_type": "sandbox.audit.result", "completion": "suspend"}}});

export const resource_77 = defineCapability({"id": "sandbox.host_math", "targets": ["browser", "node"], "operations": {"double": {"input_type": "sandbox.number", "output_type": "sandbox.math.result", "completion": "immediate"}}});

export const resource_78 = defineCapability({"id": "sandbox.storage", "targets": ["browser", "node"], "operations": {"read": {"input_type": "sandbox.storage.read.request", "output_type": "sandbox.storage.read.result", "completion": "suspend"}}});









export const resource_83 = defineRule({"id": "sandbox.domain_audit", "outputs": {"audit": "sandbox.audit.v1"}, "implementations": [{"language": "typescript", "source": {"kind": "file", "ref": "rules/domain_audit.ts", "export": "check"}}]});

export const resource_84 = defineRuleset({"id": "sandbox.domain", "calls": [{"id": "audit", "rule_id": "sandbox.domain_audit"}], "entrypoints": {"static": ["audit"], "run": ["audit"]}});

export const lifecycleType=defineNodeType({id:"sandbox.lifecycle",display_name:"Lifecycle API",presentation:{shape:"hex",fill:"#d4ead1"}});
export const windowSession=defineCapability({id:"sandbox.window_session",targets:["browser"],operations:{
 open:{input_type:"sandbox.null",output_type:"sandbox.null",completion:"immediate"},
 close:{input_type:"sandbox.null",output_type:"sandbox.null",completion:"immediate"}}});
export const mathSession=defineCapability({id:"sandbox.math_session",targets:["browser","node"],operations:{
 open:{input_type:"sandbox.null",output_type:"sandbox.null",completion:"immediate"},
 close:{input_type:"sandbox.null",output_type:"sandbox.null",completion:"immediate"},
 double:{input_type:"sandbox.number",output_type:"sandbox.math.result",completion:"immediate"}}});
export const nullSchema=defineDataSchema({type_key:"sandbox.null",schema:{type:"null"}});
export const plugin = definePlugin({id:"fixture.resources", resources:[lifecycleType,windowSession,mathSession,nullSchema, portCapability, portSchema0, portSchema1, portSchema2, portSchema3, resource_45, resource_46, resource_47, resource_48, resource_49, resource_50, resource_51, resource_52, resource_53, resource_54, resource_55, resource_56, resource_57, resource_58, resource_59, resource_60, resource_61, resource_62, resource_63, resource_64, resource_65, resource_66, resource_67, resource_68, resource_69, resource_70, resource_71, resource_72, resource_73, resource_74, resource_75, resource_76, resource_77, resource_78, resource_83, resource_84]});
