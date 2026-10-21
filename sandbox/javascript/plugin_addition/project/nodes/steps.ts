import {defineNode} from "@vibeflow/plugin";
import {library} from "../plugins/addition/math_resource.ts";
import {number} from "./node_support.ts";
export const boundary = defineNode({"node_type":"vibeflow.node",id:"addition.boundary", flow_kind:"terminal", rulesets:["vibeflow.process"], contract:{}, run(){return {};}});
export const add = defineNode({"node_type":"vibeflow.node",id:"addition.add", flow_kind:"process", rulesets:["vibeflow.process"], base_libs:["addition.math"], implementation_files:["node_support.ts"], contract:{requires:[{type:"addition.a",cardinality:"exactly_one",display_name:"A"}], provides:[{key:"result",type:"addition.result",display_name:"Sum"}], input_semantics:{"addition.a":["First addend"]}, output_semantics:{result:["Sum"]}, params_schema:{b:{type:"number"}}, params_defaults:{b:3}}, run(inputs,params){return {result:library.implementation(number(inputs),Number(params.b))};}});
