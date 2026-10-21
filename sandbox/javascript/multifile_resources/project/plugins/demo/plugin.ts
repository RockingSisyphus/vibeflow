import {definePlugin,defineCapability,defineDataSchema} from "@vibeflow/plugin";
import {lifecycle} from "./plugin_support.ts";
export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});
export const plugin=definePlugin({id:"demo",resources:[number],runtime(){return lifecycle();},rulesets:["vibeflow.plugin"],declaration_rulesets:["vibeflow.plugin_declaration"],implementation_files:["plugin_support.ts"],presentation:{fill:"#ecd4ff",shape:"cloud",icon:"P"}});
