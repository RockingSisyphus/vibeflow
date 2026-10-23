// Business arithmetic only; official Nodes own every cross-workflow operation.
import {defineNode} from "@vibeflow/plugin";

const value=(inputs,kind)=>inputs[kind].value;
const check=(condition,message)=>{if(!condition)throw Error(message);};

export const secondSeed=defineNode({id:"math.second_seed",node_type:"vibeflow.node",rulesets:["vibeflow.process"],contract:{
  requires:[{type:"math.request",cardinality:"exactly_one",display_name:"Request"},{type:"math.reply",cardinality:"exactly_one",display_name:"Reply"}],
  provides:[{key:"request_forward",type:"math.request",display_name:"Request"},{key:"reply_forward",type:"math.reply",display_name:"Reply"}],
  input_semantics:{"math.request":["First round input"],"math.reply":["First round result"]},
  output_semantics:{request_forward:["Retained input"],reply_forward:["Retained result"]}},
  run(inputs){return {request_forward:value(inputs,"math.request"),reply_forward:value(inputs,"math.reply")};}});

export const boundary=defineNode({id:"math.boundary",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[],run(){return {};}});

export const seed=defineNode({"id":"math.seed","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.stop","cardinality":"optional_one","display_name":"Stop"},{"type":"math.x","cardinality":"exactly_one","display_name":"math.x"},{"type":"math.y","cardinality":"exactly_one","display_name":"math.y"},{"type":"math.case_id","cardinality":"exactly_one","display_name":"math.case_id"}],"provides":[{"key":"seed","type":"math.seed","display_name":"seed"}],"input_semantics":{"math.stop":["Request early cancellation"],"math.x":["Formula input"],"math.y":["Formula input"],"math.case_id":["Formula input"]},"output_semantics":{"seed":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs,params,context){
    const x=value(inputs,"math.x"),y=value(inputs,"math.y");
    return {seed:{x,y,u:3*x+y,v:y-4,case_id:value(inputs,"math.case_id"),a_id:context.workflow.self().id,stop:inputs["math.stop"]?.value||false}};
  }});

export const request=defineNode({"id":"math.request","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.seed","cardinality":"exactly_one","display_name":"math.seed"}],"provides":[{"key":"request_payload","type":"example.payload","display_name":"request_payload"}],"input_semantics":{"math.seed":["Formula input"]},"output_semantics":{"request_payload":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs,params){
    const seed=value(inputs,"math.seed");let {u,v}=seed;
    if(params.fault==="swap")[u,v]=[v,u];
    if(params.fault==="send_x")u=seed.x;
    return {request_payload:{phase:"request",u,v,case_id:seed.case_id}};
  }});

export const local=defineNode({"id":"math.local","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.seed","cardinality":"exactly_one","display_name":"math.seed"}],"provides":[{"key":"r","type":"math.local","display_name":"r"}],"input_semantics":{"math.seed":["Formula input"]},"output_semantics":{"r":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs){const seed=value(inputs,"math.seed");return {r:7*seed.x-3*seed.v};}});

export const continuation=defineNode({"id":"math.continuation","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.seed","cardinality":"exactly_one","display_name":"math.seed"},{"type":"math.local","cardinality":"exactly_one","display_name":"math.local"},{"type":"example.message","cardinality":"exactly_one","display_name":"example.message"},{"type":"example.instance","cardinality":"exactly_one","display_name":"example.instance"}],"provides":[{"key":"next_payload","type":"example.payload","display_name":"next_payload"},{"key":"checkpoint","type":"math.checkpoint","display_name":"checkpoint"}],"input_semantics":{"math.seed":["Formula input"],"math.local":["Formula input"],"example.message":["Formula input"],"example.instance":["Formula input"]},"output_semantics":{"next_payload":["Formula intermediate"],"checkpoint":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},run(inputs,params){
    const seed=value(inputs,"math.seed"),message=value(inputs,"example.message"),reply=message.payload,peer=value(inputs,"example.instance");
    check(message.sender===peer&&peer===reply.b_id,"reply from wrong B instance");
    check(reply.a_id===seed.a_id&&reply.case_id===seed.case_id,"crossed calculation");
    check(reply.phase==="reply","wrong message round");
    const q=params.fault==="skip_local"?reply.b:reply.b-value(inputs,"math.local");
    return {next_payload:{phase:"continuation",q,case_id:seed.case_id},checkpoint:{...reply,q}};
  }});

export const finishA=defineNode({"id":"math.finish_a","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.seed","cardinality":"exactly_one","display_name":"math.seed"},{"type":"math.local","cardinality":"exactly_one","display_name":"math.local"},{"type":"math.checkpoint","cardinality":"exactly_one","display_name":"math.checkpoint"},{"type":"example.result","cardinality":"exactly_one","display_name":"example.result"},{"type":"example.instance","cardinality":"exactly_one","display_name":"example.instance"}],"provides":[{"key":"answer","type":"math.answer","display_name":"answer"}],"input_semantics":{"math.seed":["Formula input"],"math.local":["Formula input"],"math.checkpoint":["Formula input"],"example.result":["Formula input"],"example.instance":["Formula input"]},"output_semantics":{"answer":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs,params){
    const seed=value(inputs,"math.seed"),checkpoint=value(inputs,"math.checkpoint"),terminal=value(inputs,"example.result");
    check(terminal.id===value(inputs,"example.instance")&&terminal.state==="succeeded",JSON.stringify(terminal));
    const ended=terminal.outputs.computed;
    check(ended.case_id===seed.case_id&&ended.q===checkpoint.q,"wrong terminal output");
    const d=ended.d,result=3*(params.fault==="early_result"?checkpoint.b:d)+seed.u;
    return {answer:{result,case_id:seed.case_id,identities:{a:seed.a_id,b:checkpoint.b_id,c:checkpoint.c_id},
      stages:{u:seed.u,v:seed.v,p:checkpoint.p,b:checkpoint.b,r:value(inputs,"math.local"),q:checkpoint.q,d}}};
  }});

export const unpack=defineNode({"id":"math.unpack","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"example.message","cardinality":"exactly_one","display_name":"example.message"}],"provides":[{"key":"request","type":"math.request","display_name":"request"},{"key":"sync_payload","type":"example.payload","display_name":"sync_payload"}],"input_semantics":{"example.message":["Formula input"]},"output_semantics":{"request":["Formula intermediate"],"sync_payload":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs){
    const message=value(inputs,"example.message");check(message.payload.phase==="request","wrong message round");
    const request={...message.payload,a_id:message.sender};return {request,sync_payload:{request}};
  }});

export const reply=defineNode({"id":"math.reply","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.request","cardinality":"exactly_one","display_name":"math.request"},{"type":"example.result","cardinality":"exactly_one","display_name":"example.result"}],"provides":[{"key":"reply","type":"math.reply","display_name":"reply"},{"key":"reply_payload","type":"example.payload","display_name":"reply_payload"},{"key":"instance","type":"example.instance","display_name":"instance"}],"input_semantics":{"math.request":["Formula input"],"example.result":["Formula input"]},"output_semantics":{"reply":["Formula intermediate"],"reply_payload":["Formula intermediate"],"instance":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs,params,context){
    const request=value(inputs,"math.request"),computed=value(inputs,"example.result").computed;
    check(computed.case_id===request.case_id,"wrong synchronous result");
    const reply={phase:"reply",case_id:request.case_id,p:computed.p,b:2*computed.p-request.u,
      a_id:request.a_id,b_id:context.workflow.self().id,c_id:computed.c_id};
    check(new Set([reply.a_id,reply.b_id,reply.c_id]).size===3,"shared workflow identity");
    return {reply,reply_payload:reply,instance:request.a_id};
  }});

export const finishB=defineNode({"id":"math.finish_b","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.request","cardinality":"exactly_one","display_name":"math.request"},{"type":"math.reply","cardinality":"exactly_one","display_name":"math.reply"},{"type":"example.message","cardinality":"exactly_one","display_name":"example.message"}],"provides":[{"key":"answer","type":"math.answer","display_name":"answer"}],"input_semantics":{"math.request":["Formula input"],"math.reply":["Formula input"],"example.message":["Formula input"]},"output_semantics":{"answer":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs){
    const request=value(inputs,"math.request"),reply=value(inputs,"math.reply"),message=value(inputs,"example.message"),continuation=message.payload;
    check(message.sender===reply.a_id&&continuation.case_id===request.case_id,"crossed continuation");
    check(continuation.phase==="continuation","wrong message round");
    return {answer:{case_id:request.case_id,q:continuation.q,d:continuation.q+2*request.v}};
  }});

export const shift=defineNode({"id":"math.shift","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.request","cardinality":"exactly_one","display_name":"math.request"}],"provides":[{"key":"shift","type":"math.shift","display_name":"shift"}],"input_semantics":{"math.request":["Formula input"]},"output_semantics":{"shift":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs,params,context){const request=value(inputs,"math.request");return {shift:{...request,t:request.u-2*request.v,c_id:context.workflow.self().id}};}});
export const square=defineNode({"id":"math.square","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.shift","cardinality":"exactly_one","display_name":"math.shift"}],"provides":[{"key":"square","type":"math.square","display_name":"square"}],"input_semantics":{"math.shift":["Formula input"]},"output_semantics":{"square":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs){const shifted=value(inputs,"math.shift");return {square:{...shifted,s:shifted.t**2}};}});
export const bias=defineNode({"id":"math.bias","node_type":"vibeflow.node","rulesets":["vibeflow.process"],"contract":{"requires":[{"type":"math.square","cardinality":"exactly_one","display_name":"math.square"}],"provides":[{"key":"answer","type":"math.answer","display_name":"answer"}],"input_semantics":{"math.square":["Formula input"]},"output_semantics":{"answer":["Formula intermediate"]},"params_schema":{"fault":{"type":"string"}},"params_defaults":{"fault":""}},
  run(inputs){const squared=value(inputs,"math.square");return {answer:{p:squared.s+5*squared.v,case_id:squared.case_id,c_id:squared.c_id}};}});

export const normalSeed=defineNode({"id": "math.normal_seed", "node_type": "vibeflow.node", "rulesets": ["vibeflow.process"], "contract": {"requires": [{"type": "math.seed", "cardinality": "exactly_one", "display_name": "math.seed"}, {"type": "math.local", "cardinality": "exactly_one", "display_name": "math.local"}, {"type": "example.message", "cardinality": "exactly_one", "display_name": "example.message"}, {"type": "example.instance", "cardinality": "exactly_one", "display_name": "example.instance"}], "provides": [{"key": "seed_forward", "type": "math.seed", "display_name": "seed_forward"}, {"key": "local_forward", "type": "math.local", "display_name": "local_forward"}, {"key": "reply_forward", "type": "example.message", "display_name": "reply_forward"}, {"key": "instance_forward", "type": "example.instance", "display_name": "instance_forward"}], "input_semantics": {"math.seed": ["Retain first round input"], "math.local": ["Retain first round input"], "example.message": ["Retain first round input"], "example.instance": ["Retain first round input"]}, "output_semantics": {"seed_forward": ["Forward to the normal completion nodes"], "local_forward": ["Forward to the normal completion nodes"], "reply_forward": ["Forward to the normal completion nodes"], "instance_forward": ["Forward to the normal completion nodes"]}},
 run(inputs){return {seed_forward:value(inputs,"math.seed"),local_forward:value(inputs,"math.local"),reply_forward:value(inputs,"example.message"),instance_forward:value(inputs,"example.instance")};}});
