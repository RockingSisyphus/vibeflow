import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension,defineResource} from "@vibeflow/plugin";
export const resource_0 = defineResource({"kind": "plugin", "id": "sandbox.compiler_audit", "type": "compiler", "targets": ["browser", "node"], "priority": 20, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "plugins/compiler_audit.ts", "export": "createPlugin"}}], "rulesets": ["vibeflow.plugin"]});

export const plugin = definePlugin({id:"sandbox.compiler_audit", resources:[resource_0]});
