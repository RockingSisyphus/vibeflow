import {definePlugin,defineResource} from "@vibeflow/plugin";
const runtime = defineResource({kind:"plugin",id:"addition.runtime",type:"runtime",targets:["node","browser"],implementations:[{language:"typescript",targets:["node","browser"],completion:"immediate",source:{kind:"file",ref:"plugin_support.ts",export:"createPlugin"}}],config:{schema:{type:"object",properties:{expectedNodes:{type:"integer"}},required:["expectedNodes"],additionalProperties:false},defaults:{expectedNodes:6}},rulesets:["vibeflow.plugin"]});
export const plugin=definePlugin({id:"addition.runtime",resources:[runtime]});
