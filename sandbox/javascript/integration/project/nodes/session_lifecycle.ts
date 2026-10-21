import {defineNode} from "@vibeflow/plugin";
export const windowOpen=defineNode({id:"sandbox.window_open",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{},
 rulesets:["vibeflow.io",{rule_id:"vibeflow.capability.allow",params:{capability:"sandbox.window_session",operations:["open"]}}],capabilities:[{id:"sandbox.window_session",operations:["open"]}],
 run(inputs,params,context){context.capabilities["sandbox.window_session"].open(null);return {};}});
export const windowClose=defineNode({id:"sandbox.window_close",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{},
 rulesets:["vibeflow.io",{rule_id:"vibeflow.capability.allow",params:{capability:"sandbox.window_session",operations:["close"]}}],capabilities:[{id:"sandbox.window_session",operations:["close"]}],
 run(inputs,params,context){context.capabilities["sandbox.window_session"].close(null);return {};}});
export const mathOpen=defineNode({id:"sandbox.math_open",node_type:"sandbox.lifecycle",flow_kind:"io",
 contract:{requires:[{type:"sandbox.number",cardinality:"exactly_one",display_name:"Number"}],
 provides:[{key:"opened_x",type:"sandbox.number",display_name:"Number"}],
 input_semantics:{"sandbox.number":["Value passed into the opened math session"]},
 output_semantics:{opened_x:["Unchanged value for the calculation"]}},
 rulesets:["vibeflow.io",{rule_id:"vibeflow.capability.allow",params:{capability:"sandbox.math_session",operations:["open"]}}],capabilities:[{id:"sandbox.math_session",operations:["open"]}],
 run(inputs,params,context){context.capabilities["sandbox.math_session"].open(null);return {opened_x:inputs["sandbox.number"].value};}});
export const mathClose=defineNode({id:"sandbox.math_close",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{},
 rulesets:["vibeflow.io",{rule_id:"vibeflow.capability.allow",params:{capability:"sandbox.math_session",operations:["close"]}}],capabilities:[{id:"sandbox.math_session",operations:["close"]}],
 run(inputs,params,context){context.capabilities["sandbox.math_session"].close(null);return {};}});
