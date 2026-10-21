import {definePlugin,defineResource,defineDataSchema} from "@vibeflow/plugin";
import {library} from "./math_resource.ts";
export const plugin = definePlugin({id:"addition.plugin",resources:[library,defineDataSchema({type_key:"addition.a",schema:{type:"number"}}),defineDataSchema({type_key:"addition.result",schema:{type:"number"}})]});
