/* Protocol and graph projection. Architecture facts are the only semantic input. */
"use strict";
window.VFModel = (()=>{
  function bodies(architecture,graphs={},workflow={}) {
    const result={};
    function register(architecture,identity,namespace=""){
      const key=namespace+"workflow",body={key,namespace,architecture,identity,kind:"workflow",facts:architecture.workflow||{nodes:[],edges:[]},direction:"DOWN"};
      result[key]=body;if(identity?.id)result["@workflow:"+identity.id]=body;
      for(const [name,entry] of Object.entries(body.facts.entries||{})){
        const active=new Set(entry.nodes||[]),nodes=Array.isArray(body.facts.nodes)?body.facts.nodes:Object.values(body.facts.nodes||{});
        const entryKey=namespace+"entry:"+encodeURIComponent(name);
        result[entryKey]={...body,key:entryKey,facts:{...body.facts,selected_entry:name,nodes:nodes.filter(n=>active.has(n.id)),
          edges:(body.facts.edges||[]).filter(e=>active.has(e.from)&&active.has(e.to)),inputs:entry.inputs,outputs:entry.outputs}};
      }
      for(const [name,definition] of Object.entries(architecture.nodeset_types||{}))if(definition.body){
        const childKey=namespace+"nodeset:"+name;
        result[childKey]={key:childKey,namespace,architecture,identity,kind:"nodeset",facts:definition.body,direction:"DOWN"};
      }
    }
    register(architecture,workflow);
    for(const [id,item] of Object.entries(graphs))register(item.architecture,item.workflow,"workflow:"+id+":");
    const resources=architecture.implementation_graph||{};
    result.resources={facts:{nodes:Object.entries(resources.resources||{}).map(([id,facts])=>({...facts,resource_id:facts.id,id})),
      edges:(resources.relations||[]).filter(e=>resources.resources?.[e.from]&&resources.resources?.[e.to])},direction:"RIGHT"};
    return result;
  }
  function childOptions(facts,body,localPath,all){
    if(facts.invokes){const key=body.namespace+"nodeset:"+facts.invokes.target,nodes=all[key]?.facts.nodes,available=nodes&&(Array.isArray(nodes)?nodes.length:Object.keys(nodes).length);return [{key,label:facts.invokes.target,workflow:false,error:available?"":"内部定义不可用"}];}
    const declarations=body.architecture?.workflow?.workflow_targets||{},actions=body.architecture?.call_policies?.[JSON.stringify(localPath)]?.actions||[];
    return actions.filter(a=>a.capability==="vibeflow.workflow"&&a.target).map(action=>{
      const target=declarations[action.target],root=target&&all["@workflow:"+target.identity],entry=action.entry||target?.entry||root?.facts.default_entry||(Object.keys(root?.facts.entries||{}).length===1?Object.keys(root.facts.entries)[0]:null);
      const key=entry&&root?root.namespace+"entry:"+encodeURIComponent(entry):root?.key;
      return {key,label:action.target+(entry?" / "+entry:" / 全部入口"),workflow:true,
        error:target?.preview_error||(!target?"未声明目标 workflow":!all[key]?"本次未准备此目标或入口的事实":"")};
    });
  }
  function resourceView(body,kinds){
    const selected=new Set(kinds),resources=body.facts.nodes;
    const packages=new Set(resources.filter(r=>r.kind==="plugin_declaration").map(r=>r.resource_id));
    const nodes=resources.filter(r=>selected.has(r.kind)&&!(r.kind==="base_lib"&&r.owner?.kind==="plugin")&&!(r.kind==="plugin"&&packages.has(r.plugin_id)));
    const ids=new Set(nodes.map(r=>r.id));
    return {...body,facts:{nodes,edges:body.facts.edges.filter(e=>ids.has(e.from)&&ids.has(e.to))}};
  }
  function operationLabel(action){
    if(action.operation==="call")return action.wait===true?"启动 workflow · 等待结束":"启动 workflow · 不等待结束";
    return ({self:"本实例身份",wait:"等待实例结束",send:"发送消息 · 不等待处理",receive:"接收消息 · 等待",kill:"停止实例 · 确认终态"})[action.operation]||action.operation;
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
  return {bodies,childOptions,resourceView,operationLabel,nodeInfo,edgeInfo,graphEdges,edgeLabel,loadScript};
})();
