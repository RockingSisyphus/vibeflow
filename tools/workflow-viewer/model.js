/* Protocol and graph projection. Architecture facts are the only semantic input. */
"use strict";
window.VFModel = (()=>{
  function bodies(architecture) {
    const result={workflow:{facts:architecture.workflow||{nodes:[],edges:[]},direction:"DOWN"}};
    for(const [key,definition] of Object.entries(architecture.nodesets||{}))
      if(definition.body)result["nodeset:"+key]={facts:definition.body,direction:"DOWN"};
    const resources=architecture.implementation_graph||{};
    result.resources={facts:{nodes:Object.entries(resources.resources||{}).map(([id,facts])=>({...facts,resource_id:facts.id,id})),
      edges:(resources.relations||[]).filter(e=>resources.resources?.[e.from]&&resources.resources?.[e.to])},direction:"RIGHT"};
    return result;
  }
  const roleNames={mainline:"流程主线",schedule:"触发调度",transfer:"允许数据传递",data_bypass:"仅传递数据"};
  function nodeInfo(facts,architecture={}) {
    const type=architecture.node_types?.[facts.type_used||facts.type_key]||null;
    const definition=facts.invokes?architecture.nodesets?.[facts.invokes.target]||null:null;
    const resource=architecture.implementation_graph?.resources?.["node:"+(facts.type_used||facts.type_key)]||null;
    const typeInfo=type?.info||type||{},contract=facts.contract||type?.contract||resource?.contract||{};
    const status=[facts.status,facts.invokes?.target_status,definition?.status].includes("planned")?"planned":facts.status||"implemented";
    const nodes=definition?.body?.nodes;
    return {call:facts,type,typeInfo,definition,resource,
      status,plannedBehavior:facts.planned_behavior??definition?.planned_behavior,
      expandable:Boolean(nodes&&(Array.isArray(nodes)?nodes.length:Object.keys(nodes).length)),
      description:facts.role?.description||facts.description||facts.info?.description||typeInfo.description||definition?.description||"",
      contract,config:type?.config||{schema:contract.params_schema||{},defaults:contract.params_defaults||{}}};
  }
  function edgeInfo(facts,nodes=[],architecture={},topology={}) {
    const source=nodes.find(n=>n.id===facts.from),target=nodes.find(n=>n.id===facts.to);
    const roles=facts.roles||[],scheduled=roles.includes("schedule")||roles.includes("mainline"),transfer=roles.includes("transfer")||roles.includes("data_bypass");
    const dispatch=scheduled&&source?.flow_kind!=="decision"&&(topology.outgoing?.get(facts.from)?.size||0)>1;
    const join=scheduled&&target?.join_policy==="all"&&(topology.incoming?.get(facts.to)?.size||0)>1;
    const kind=facts.relation?"relation":!scheduled&&transfer?"data":dispatch||join?"parallel":"flow";
    const labels=[dispatch?"并发分发":"",join?"等待全部分支汇合":""].filter(Boolean);
    const transfers=transfer?(facts.transfers||((source?.provides||[]).flatMap(provider=>(target?.requires||[])
      .filter(requirement=>provider.type===requirement.type).map(requirement=>({provider,requirement}))))):[];
    const lines=[...(kind==="data"?["仅传递数据"]:labels),...(facts.when?["条件："+facts.when]:[]),...(facts.relation?[facts.relation]:[])];
    for(const {provider,requirement} of transfers.slice(0,2))lines.push((provider.display_name||provider.key||provider.type)+" → "+(requirement.display_name||requirement.as||requirement.type)+" ["+provider.type+"]");
    if(transfers.length>2)lines.push("另有 "+(transfers.length-2)+" 项数据契约");
    return {facts,source,target,sourceInfo:source?nodeInfo(source,architecture):null,targetInfo:target?nodeInfo(target,architecture):null,
      roles,roleLabels:roles.map(r=>roleNames[r]||r),scheduled,transfer,dispatch,join,kind,transfers,lines,
      label:kind==="data"?"仅传递数据":kind==="parallel"?labels.join(" · "):kind==="relation"?"资源 / workflow 关系":"正常流程"};
  }
  function graphEdges(body,architecture={}) {
    const nodes=Array.isArray(body.nodes)?body.nodes:Object.values(body.nodes||{}),topology={outgoing:new Map(),incoming:new Map()};
    for(const edge of body.edges||[])if(edge.roles?.some(r=>r==="schedule"||r==="mainline")){
      if(!topology.outgoing.has(edge.from))topology.outgoing.set(edge.from,new Set());topology.outgoing.get(edge.from).add(edge.to);
      if(!topology.incoming.has(edge.to))topology.incoming.set(edge.to,new Set());topology.incoming.get(edge.to).add(edge.from);
    }
    return (body.edges||[]).map(edge=>edgeInfo(edge,nodes,architecture,topology));
  }
  function edgeLabel(facts) {
    return edgeInfo(facts).lines.join("\n");
  }
  function loadScript(url,catalog=null) {
    return new Promise((resolve,reject)=>{
      const script=document.createElement("script");script.previewRecords=catalog;
      script.src=url+(url.includes("?")?"&":"?")+"load="+Date.now()+Math.random();
      const finish=action=>{window.removeEventListener("error",failure);script.remove();action();};
      const failure=event=>{if(event.filename===script.src)finish(()=>reject(new Error(event.message)));};
      window.addEventListener("error",failure);script.onload=()=>finish(resolve);
      script.onerror=()=>finish(()=>reject(new Error("无法加载 "+url)));document.head.append(script);
    });
  }
  return {bodies,nodeInfo,edgeInfo,graphEdges,edgeLabel,loadScript};
})();
