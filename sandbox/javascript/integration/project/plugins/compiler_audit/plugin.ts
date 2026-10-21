import {definePlugin,defineNode,defineRule,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineResource} from "@vibeflow/plugin";
export const resource_0 = defineResource({"kind": "plugin", "id": "sandbox.compiler_audit", "type": "compiler", "targets": ["browser", "node"], "priority": 20, "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "implementation.ts", "export": "createPlugin"}}], "rulesets": ["vibeflow.plugin"]});

export const plugin = definePlugin({id:"sandbox.compiler_audit", resources:[resource_0]});
