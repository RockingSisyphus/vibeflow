// Explicit cancellation path; the second-round Node owns actual async cleanup.
import {defineNode} from "@vibeflow/plugin";
const check=(condition,message)=>{if(!condition)throw Error(message);};
const value=(inputs,kind)=>inputs[kind].value;
export const choose=defineNode({id:'math.choose',node_type:'vibeflow.node',flow_kind:'decision',rulesets:['vibeflow.process'],contract:{
 requires:[{type:'math.seed',cardinality:'exactly_one',display_name:'Seed'}],provides:[{key:'stop_route',type:'math.stop',display_name:'Stop'}],
 input_semantics:{'math.seed':['Requested execution path']},output_semantics:{stop_route:['Choose explicit Kill or normal continuation']}},
 run(inputs){return {stop_route:value(inputs,'math.seed').stop};}});
export const readyToKill=defineNode({"id": "math.ready_to_kill", "node_type": "vibeflow.node", "flow_kind": "workflow-io", "completion":"suspend", "rulesets": ["vibeflow.process", {"rule_id": "vibeflow.capability.allow", "params": {"capability": "vibeflow.workflow", "operations": ["receive"]}}], "capabilities": [{"id": "vibeflow.workflow", "operations": ["receive"]}], "contract": {"requires": [{"type": "math.seed", "cardinality": "exactly_one", "display_name": "math.seed"}, {"type": "example.instance", "cardinality": "exactly_one", "display_name": "example.instance"}], "provides": [], "input_semantics": {"math.seed": ["Cancellation protocol input"], "example.instance": ["Cancellation protocol input"]}, "output_semantics": {}, "params_schema": {"expected_workflows": {"type": "array", "items": {"type": "object"}}}, "params_defaults": {"expected_workflows": []}},
 async run(inputs,params,context){
  const message=await context.capabilities['vibeflow.workflow'].receive({port:'ready'});
  check(message.sender===value(inputs,'example.instance')&&message.payload.case_id===value(inputs,'math.seed').case_id,'wrong readiness message');return {};
 }});
export const receiveNext=defineNode({"id": "math.receive_next", "node_type": "vibeflow.node", "flow_kind": "workflow-io", "completion":"suspend", "rulesets": ["vibeflow.process", {"rule_id": "vibeflow.capability.allow", "params": {"capability": "vibeflow.workflow", "operations": ["send", "receive"]}}], "capabilities": [{"id": "vibeflow.workflow", "operations": ["send", "receive"]}], "contract": {"requires": [{"type": "math.request", "cardinality": "exactly_one", "display_name": "math.request"}, {"type": "math.reply", "cardinality": "exactly_one", "display_name": "math.reply"}], "provides": [{"key": "message", "type": "example.message", "display_name": "message"}], "input_semantics": {"math.request": ["Cancellation protocol input"], "math.reply": ["Cancellation protocol input"]}, "output_semantics": {"message": ["Cancellation protocol result"]}, "params_schema": {"expected_workflows": {"type": "array", "items": {"type": "object"}}}, "params_defaults": {"expected_workflows": []}},
 async run(inputs,params,context){
  const request=value(inputs,'math.request'),reply=value(inputs,'math.reply'),api=context.capabilities['vibeflow.workflow'];
  try{
   api.send({id:request.a_id,port:'ready',payload:{case_id:request.case_id}});
   return {message:await api.receive({})};
  }finally{
   await new Promise(resolve=>setTimeout(resolve,10));
   api.send({id:request.a_id,port:'cleanup',payload:{case_id:request.case_id,c_id:reply.c_id,cleanup:'finished'}});
  }
 }});
export const cancelled=defineNode({"id": "math.cancelled", "node_type": "vibeflow.node", "flow_kind": "workflow-io", "completion":"suspend", "rulesets": ["vibeflow.process", {"rule_id": "vibeflow.capability.allow", "params": {"capability": "vibeflow.workflow", "operations": ["receive"]}}], "capabilities": [{"id": "vibeflow.workflow", "operations": ["receive"]}], "contract": {"requires": [{"type": "math.seed", "cardinality": "exactly_one", "display_name": "math.seed"}, {"type": "example.result", "cardinality": "exactly_one", "display_name": "example.result"}], "provides": [{"key": "answer", "type": "math.answer", "display_name": "answer"}], "input_semantics": {"math.seed": ["Cancellation protocol input"], "example.result": ["Cancellation protocol input"]}, "output_semantics": {"answer": ["Cancellation protocol result"]}, "params_schema": {"expected_workflows": {"type": "array", "items": {"type": "object"}}}, "params_defaults": {"expected_workflows": []}},
 async run(inputs,params,context){
  const seed=value(inputs,'math.seed'),status=value(inputs,'example.result');
  check(status.state==='cancelled'&&status.outputs===null,'Kill did not report cancellation without output');
  const message=await context.capabilities['vibeflow.workflow'].receive({port:'cleanup',timeout:0});
  check(message.sender===status.id&&message.payload.case_id===seed.case_id&&message.payload.cleanup==='finished','cleanup was not complete when Kill returned');
  return {answer:{status:'cancelled',case_id:seed.case_id,cleanup:'finished',identities:{a:context.workflow.self().id,b:status.id,c:message.payload.c_id}}};
 }});
