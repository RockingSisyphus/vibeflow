import {definePlugin,defineCapability,defineDataSchema} from "@vibeflow/plugin";
import {model,start} from "./node.ts";
import {library} from "./math.ts";
import {host} from "./host.ts";
import {lifecycle} from "./plugin_support.ts";
export const session=defineCapability({id:"demo.session",targets:["node","browser"],operations:{next:{input_type:"number",output_type:"number",completion:"immediate"}}});
export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});
export const plugin=definePlugin({id:"demo",resources:[start,model,library,host,session,number],runtime(){return lifecycle();},rulesets:["vibeflow.plugin"],declaration_rulesets:["vibeflow.plugin_declaration"],implementation_files:["plugin_support.ts"],presentation:{fill:"#ecd4ff",shape:"cloud",icon:"P"}});
