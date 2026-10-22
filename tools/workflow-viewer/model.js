/* Protocol and graph projection. Architecture facts are the only semantic input. */
"use strict";
window.VFModel = (()=>{
  function bodies(architecture,workflow={}) {
    const result={};
    const key="workflow",body={key,architecture,identity:workflow,kind:"workflow",facts:architecture.workflow||{nodes:[],edges:[]},direction:"DOWN"};
    result[key]=body;
    for(const [name,entry] of Object.entries(body.facts.entries||{})){
      const active=new Set(entry.nodes||[]),nodes=Array.isArray(body.facts.nodes)?body.facts.nodes:Object.values(body.facts.nodes||{});
      const entryKey="entry:"+encodeURIComponent(name);
      result[entryKey]={...body,key:entryKey,facts:{...body.facts,selected_entry:name,nodes:nodes.filter(n=>active.has(n.id)),
        edges:(body.facts.edges||[]).filter(e=>active.has(e.from)&&active.has(e.to)),inputs:entry.inputs,outputs:entry.outputs}};
    }
    for(const [name,definition] of Object.entries(architecture.nodeset_types||{}))if(definition.body){
      const childKey="nodeset:"+name;
      result[childKey]={key:childKey,architecture,identity:workflow,kind:"nodeset",facts:definition.body,direction:"DOWN"};
    }
    const resources=architecture.implementation_graph||{};
    result.resources={facts:{nodes:Object.entries(resources.resources||{}).map(([id,facts])=>({...facts,resource_id:facts.id,id})),
      edges:(resources.relations||[]).filter(e=>resources.resources?.[e.from]&&resources.resources?.[e.to])},direction:"RIGHT"};
    return result;
  }
  function childOptions(facts,body,localPath,all){
    if(facts.invokes){const key="nodeset:"+facts.invokes.target,nodes=all[key]?.facts.nodes,available=nodes&&(Array.isArray(nodes)?nodes.length:Object.keys(nodes).length);return [{key,label:facts.invokes.target,error:available?"":"内部定义不可用"}];}
    return [];
  }
  function workflowTarget(ref,graphs={},selectDefault=false){
    const id=ref.root+":"+ref.path,target=graphs[id]?.architecture?.workflow,names=Object.keys(target?.entries||{});
    const entry=ref.entry||(selectDefault?(target?.default_entry||(names.length===1?names[0]:"")):"");
    return {id,entry,error:graphs[id]?.error||(selectDefault&&names.length>1&&!entry?"多入口且无默认值；请配置 workflow.entry":"")};
  }
  function workflowOptions(facts,architecture,localPath,graphs={}){
    const actions=architecture.call_policies?.[JSON.stringify(localPath)]?.actions||facts.operations||[];
    const result=new Map();
    for(const action of actions){
      if(action.capability!=="vibeflow.workflow")continue;
      const refs=action.workflow?[action.workflow]:action.expected_workflows||[];
      for(const ref of refs){
        const {id,entry,error}=workflowTarget(ref,graphs,action.operation==="call"),key=id+"|"+entry;
        result.set(key,{id,entry,workflow:ref,
          label:id+(entry?" · 入口 "+entry:"")+(action.expected_workflows?" · 预期交互":""),error});
      }
    }
    return [...result.values()];
  }

  function resourceView(body,kinds){
    const selected=new Set(kinds),resources=body.facts.nodes;
    const packages=new Set(resources.filter(r=>r.kind==="plugin_declaration").map(r=>r.resource_id));
    const nodes=resources.filter(r=>selected.has(r.kind)&&!(r.kind==="base_lib"&&r.owner?.kind==="plugin")&&!(r.kind==="plugin"&&packages.has(r.plugin_id)));
    const ids=new Set(nodes.map(r=>r.id));
    return {...body,facts:{nodes,edges:body.facts.edges.filter(e=>ids.has(e.from)&&ids.has(e.to))}};
  }
  function operationLabel(action){
    if(action.planned&&action.operation==="call")return "计划启动 workflow";
    if(action.operation==="call")return action.wait===true?"启动 workflow · 等待结束":"启动 workflow · 不等待结束";
    return ({wait:"等待实例结束",send:"发送消息 · 不等待处理",receive:"接收消息 · 等待",kill:"停止实例 · 确认终态"})[action.operation]||action.operation;
  }
  function workflowOperation(actions){
    const operations=new Set(actions.filter(a=>a.capability==="vibeflow.workflow").map(a=>a.operation));
    const primary=[...operations].filter(op=>op!=="wait"),visible=primary.length?primary:[...operations];
    return visible.length===1?visible[0]:visible.length?"multiple":"";
  }
  function operationTitle(action){
    const name=({call:action.wait?"启动并等待":"启动",kill:"停止",send:"发送",receive:"接收",wait:"等待结束"})[action.operation]||action.operation;
    return action.operation.toUpperCase()+" · "+name;
  }
  const roleNames={mainline:"流程主线",schedule:"触发调度",transfer:"允许数据传递",data_bypass:"仅传递数据"};
  function nodeInfo(facts,architecture={}) {
    const nodeDefinition=architecture.node_definitions?.[facts.definition_id]||null;
    const nodeType=architecture.node_types?.[nodeDefinition?.node_type]||null;
    const definition=facts.invokes?architecture.nodeset_types?.[facts.invokes.target]||null:null;
    const resource=architecture.implementation_graph?.resources?.["node:"+facts.definition_id]||null;
    const definitionInfo=nodeDefinition?.info||nodeDefinition||{},contract=facts.contract||nodeDefinition?.contract||resource?.contract||{};
    const status=[facts.status,facts.invokes?.target_status,definition?.status].includes("planned")?"planned":facts.status||"implemented";
    const nodes=definition?.body?.nodes;
    return {call:facts,nodeDefinition,nodeType,definitionInfo,definition,resource,
      status,plannedBehavior:facts.planned_behavior??definition?.planned_behavior,
      expandable:Boolean(facts.preview_expandable||nodes&&(Array.isArray(nodes)?nodes.length:Object.keys(nodes).length)),
      description:facts.role?.description||facts.description||facts.info?.description||definitionInfo.description||definition?.description||"",
      contract,config:nodeDefinition?.config||{schema:contract.params_schema||{},defaults:contract.params_defaults||{}}};
  }
  function edgeInfo(facts,nodes=[],architecture={},topology={}) {
    const source=nodes.find(n=>n.id===facts.from),target=nodes.find(n=>n.id===facts.to);
    const roles=facts.roles||[],scheduled=roles.includes("schedule")||roles.includes("mainline"),transfer=roles.includes("transfer")||roles.includes("data_bypass");
    const dispatch=scheduled&&source?.flow_kind!=="decision"&&(topology.outgoing?.get(facts.from)?.size||0)>1;
    const join=scheduled&&target?.join_policy==="all"&&(topology.incoming?.get(facts.to)?.size||0)>1;
    const kind=facts.relation?"relation":!scheduled&&transfer?"data":dispatch||join?"parallel":"flow";
    const labels=[dispatch?"并发分发":"",join?(topology.allEntries?"按入口等待有效分支汇合":"等待全部分支汇合"):""].filter(Boolean);
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
    const nodes=Array.isArray(body.nodes)?body.nodes:Object.values(body.nodes||{}),topology={outgoing:new Map(),incoming:new Map(),allEntries:Object.keys(body.entries||{}).length&&!body.selected_entry};
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
  return {bodies,childOptions,workflowTarget,workflowOptions,resourceView,operationLabel,workflowOperation,operationTitle,nodeInfo,edgeInfo,graphEdges,edgeLabel,loadScript};
})();
