/* Hierarchical placement of data-driven cards with bundled ELK. */
"use strict";
window.VFLayout={async body(context,key,prefix="",ancestors=[],override=null,entity="call",localPrefix=[]){
  const {data,state,elk}=context;
  if(!elk)throw new Error("离线 ELK 布局资源缺失。");
  const body=override||data.bodies[key];if(!body)throw new Error("缺少图定义 "+key);
  if(ancestors.includes(key)&&body.kind!=="workflow")throw new Error("Nodeset 定义形成递归："+ancestors.concat(key).join(" → "));
  const architecture=body.architecture||data.architecture;
  const facts=Array.isArray(body.facts.nodes)?body.facts.nodes:Object.values(body.facts.nodes||{});
  const values=await Promise.all(facts.map(async original=>{
    const localPath=[...localPrefix,original.id];
    const options=VFModel.childOptions(original,body,localPath,data.bodies);
    const actions=architecture.call_policies?.[JSON.stringify(localPath)]?.actions||original.operations||[];
    const operations=actions.map(action=>{
      if(action.operation!=="call"||!action.workflow)return action;
      const {entry}=VFModel.workflowTarget(action.workflow,data.workflow_graphs,true);
      return entry?{...action,workflow:{...action.workflow,entry}}:action;
    });
    const facts={...original,preview_operations:operations,preview_expandable:options.some(o=>!o.error)};
    const segment=encodeURIComponent(facts.id),path=entity==="resource"?facts.id:prefix?prefix+"/"+segment:segment,card=VFShapes.measure(facts,architecture);
    facts.preview_presentation=card.presentation;
    const item={id:facts.id,path,localPath,body,architecture,options,facts,card,width:card.width,height:card.height};
    const selected=options.find(o=>!o.error),child=selected?.key;
    if(state.expanded.has(path)&&child&&!selected.error&&data.bodies[child]?.facts.nodes?.length){
      const childPrefix=path;
      item.inner=await VFLayout.body(context,child,childPrefix,ancestors.concat(key),null,"call",localPath);
      item.width=Math.max(360,item.inner.width+40);
      item.header=VFShapes.groupHeader(facts,architecture,item.width);
      item.height=item.header.height+item.inner.height+40;
    }
    return item;
  }));
  const edgeInfo=VFModel.graphEdges(body.facts,architecture);
  const edges=edgeInfo.map((info,i)=>{
    info.key=prefix+"/@edge/"+i;
    info.labelLines=info.lines.flatMap(line=>VFShapes.wrap(line,300,12));
    const label=info.labelLines.join("\n"),facts=info.facts;
    return {id:"edge"+i,sources:[facts.from],targets:[facts.to],...(label?{labels:[{id:"label"+i,text:label,width:Math.max(...info.labelLines.map(t=>VFShapes.width(t)))+16,height:info.labelLines.length*18+12}]}:{})};
  });
  const graph=await elk.layout({id:"root",layoutOptions:{"elk.algorithm":"layered","elk.direction":body.direction||"DOWN",
    "elk.edgeRouting":"ORTHOGONAL","elk.spacing.nodeNode":"48","elk.layered.spacing.nodeNodeBetweenLayers":"82",
    "elk.spacing.edgeNode":"24","elk.padding":"[top=24,left=24,bottom=24,right=24]"},children:values.map(v=>({id:v.id,width:v.width,height:v.height})),edges});
  return {width:graph.width||40,height:graph.height||40,values:values.map(v=>Object.assign(v,graph.children.find(n=>n.id===v.id))),
    edges:graph.edges||[],facts:body.facts.edges||[],edgeInfo,entity};
}};
