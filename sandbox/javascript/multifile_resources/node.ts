import {defineNode} from "@vibeflow/plugin";
import {library} from "./math.ts";
import {multiply} from "./node_support.ts";
export const model=defineNode({type_key:"demo.model",tags:["model_block"],base_libs:["demo.math"],implementation_files:["node_support.ts"],rulesets:["vibeflow.process"],contract:{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["Computed value"]}},presentation:{fill:"#add8e6",stroke:"#1a5276",text:"#123456",shape:"rounded",icon:"M"},run(){return {result:multiply(library.implementation(2),2)};}});
export const start=defineNode({type_key:"demo.start",flow_kind:"terminal",rulesets:[],contract:{},run(){return {};}});
