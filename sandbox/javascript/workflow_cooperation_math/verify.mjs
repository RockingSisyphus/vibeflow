// One portable driver, bundled together with real AOT modules and Coordinator.
const check=(condition,message)=>{if(!condition)throw Error(message);};

async function deadline(promise){
  let timer;
  try{return await Promise.race([promise,new Promise((_,reject)=>{
    timer=setTimeout(()=>reject(Error("cooperative formula timed out")),15000);
  })]);}finally{clearTimeout(timer);}
}

export async function verify(Coordinator, modules, cases, faults){
  const reference=name=>({root:"cooperation",path:`configs/${name}.jsonc`,entry:"calculate"});
  function host(a=modules.a){
    const scope=new Coordinator(),events=[];let active=0,peak=0;
    for(const [name,module] of Object.entries({a,b:modules.b,c:modules.c})){
      const execute=module.workflowDescriptor.entry_mode==="sync"?module.runWorkflow:module.runWorkflowAsync;
      scope.bind(module.workflowDescriptor,(inputs,options)=>{
        events.push({workflow:name,kind:"enter",id:options.workflowInstanceId});
        const settings={...options,trace:"full",onTrace:event=>events.push({workflow:name,...event})};
        if(name==="c"){
          const result=execute(inputs,settings);
          check(!result?.then,"C must return an ordinary value immediately");
          events.push({workflow:name,kind:"exit",id:options.workflowInstanceId});
          return result;
        }
        if(name==="a")peak=Math.max(peak,++active);
        return execute(inputs,settings).finally(()=>{
          if(name==="a")active--;
          events.push({workflow:name,kind:"exit",id:options.workflowInstanceId});
        });
      });
    }
    return {scope,events,peak:()=>peak};
  }
  const {scope,events,peak}=host();
  let rows,cancelled;
  try{
    const immediate=scope.invoke_sync({workflow:reference("c"),inputs:{request:{u:13,v:3,case_id:"direct"}}});
    check(!immediate.then&&immediate.computed.p===64,"direct sync result");
    check(scope.instances.size===0,"synchronous records retained");
    let refused=false;
    try{scope.invoke_sync({workflow:reference("a"),inputs:cases[0]});}
    catch(error){refused=error.code==="VF_WORKFLOW_SYNC_UNSUPPORTED";}
    check(refused,"async target accepted by InvokeSync");
    const ended=await deadline(Promise.all([...cases,{...cases[0],case_id:"case-cancelled",stop:true}].map(input=>scope.run(reference("a"),input))));
    check(ended.every(item=>item.state==="succeeded"),JSON.stringify(ended));
    rows=ended.slice(0,cases.length).map(item=>item.outputs.computed);
    cancelled=ended.at(-1).outputs.computed;
    check(cancelled.status==="cancelled"&&cancelled.cleanup==="finished"&&!("result" in cancelled)&&!("d" in cancelled),"cancelled calculation fabricated output");
    const stopped=await scope.operations(ended.at(-1).id).wait({id:cancelled.identities.b});
    check(stopped.state==="cancelled"&&stopped.outputs===null,"stopped B has numerical output");
    check(new Set([...rows,cancelled].flatMap(row=>Object.values(row.identities))).size===3*(cases.length+1),"cancellation shared an instance");
    check(peak()>1,"parent workflows did not overlap");
    check(scope.instances.size===2*(cases.length+1),"only A/B terminal records may remain");
    for(const [index,item] of ended.slice(0,cases.length).entries()){
      const row=rows[index];check(item.id===row.identities.a,"wrong parent identity");
      const again=await scope.operations(item.id).wait({id:row.identities.b});
      check(again.state==="succeeded"&&again.outputs.computed.d===row.stages.d,"terminal result not repeatable");
    }
    for(const id of [...scope.instances.keys()])scope.release(id);
    check(scope.instances.size===0,"release retained records");
  }finally{await scope.close();}
  const controls=[];
  for(const [fault,expected] of Object.entries(faults)){
    const {scope}=host(modules[fault]);
    try{
      const ended=await deadline(scope.run(reference("a"),cases[0]));
      check(ended.state==="succeeded",JSON.stringify(ended));
      const observed=ended.outputs.computed.result;
      check(observed===expected&&observed!==rows[0].result,`oracle missed ${fault}: ${observed}`);
      controls.push({fault,observed,correct:rows[0].result});
    }finally{await scope.close();}
  }
  check(events.filter(event=>event.kind==="enter").every(event=>typeof event.id==="string"),"execution trace lost workflow identity");
  return {rows,cancelled,controls,peakParents:peak(),events};
}
