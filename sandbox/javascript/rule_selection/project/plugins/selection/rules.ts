import {defineRule} from "@vibeflow/plugin";
export const analyze = defineRule({id:"selection.analyze", level:"graph", scope:"call", params_schema:{label:{type:"string"}}, params_defaults:{label:""}, outputs:{coverage:"selection.coverage"}, check(context,inputs,params) {
  const value = {label:params.label, phase:context.phase, entry:context.subject.call_path,
    graphs:context.facts.graphs.map(item=>({path:item.call_path,nodes:item.graph.nodes.map(node=>node.id)})),
    background_nodes:context.facts.global_graph.nodes.map(node=>node.id)};
  return {records:{coverage:{type_id:"selection.coverage",value}}};
}});
export const graphCheck = defineRule({id:"selection.graph_check", level:"graph", scope:"call", inputs:{coverage:"selection.coverage"}, check(context,inputs) {
  return {findings:[{code:"SELECTION.GRAPH",severity:"warning",subject_id:"selection",message:"Graph responsibility proof",details:inputs.coverage.value}]};
}});
export const localCheck = defineRule({id:"selection.local_check", scope:"call", check(context) {
  return {findings:[{code:"SELECTION.LOCAL",severity:"warning",subject_id:"selection.node",message:"Local selection proof",details:{
    phase:context.phase,path:context.subject.call_path,forbidden:["graph","global_graph","node_catalog","catalogs"].filter(key=>key in context.facts)}}]};
}});
