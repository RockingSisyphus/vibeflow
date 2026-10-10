import {definePlugin,defineResource} from "@vibeflow/plugin";
const compiler = defineResource({kind:"plugin",id:"addition.compiler",type:"compiler",targets:["node","browser"],implementations:[{language:"typescript",targets:["node","browser"],source:{kind:"file",ref:"compiler_support.ts",export:"createPlugin"}}],rulesets:["vibeflow.plugin"]});
export const plugin=definePlugin({id:"addition.compiler",resources:[compiler]});
