import {definePlugin,defineResource,defineDataSchema} from "@vibeflow/plugin";
import {add,boundary} from "./nodes.ts";
import {library} from "./math_resource.ts";
export const plugin = definePlugin({id:"addition.plugin",resources:[add,boundary,library,defineDataSchema({type_key:"addition.a",schema:{type:"number"}}),defineDataSchema({type_key:"addition.result",schema:{type:"number"}})]});
