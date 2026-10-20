/* Flow, resource and declared-workflow views over the common card renderer. */
"use strict";
window.VFViews=({getData,getMode,getCurrent,getVisible,getEdgeFacts,isCurrent,elk,node,layoutBody,factsNodes,empty,showInfo,resourceUrl})=>{
  let sequence=0;
  function arrows(group){
    const defs=node("defs"),ids={};
    for(const [kind,color] of [["flow","#37352f"],["parallel","#006d77"],["data","#716c60"],["relation","#47453e"]]){
      const id="arrow-"+(++sequence);ids[kind]=id;
      const marker=node("marker",{id,viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:7,markerHeight:7,orient:"auto"});
      marker.append(node("path",{d:kind==="data"?"M1 1 L9 5 L1 9":"M0 0 L10 5 L0 10 Z",fill:kind==="data"?"none":color,stroke:color,"stroke-width":1.3}));defs.append(marker);
    }
    group.append(defs);return ids;
  }
  function connection(group,points,info,edgeId,markers,attributes={}){
    const d=points.map((p,i)=>(i?"L":"M")+p.x+" "+p.y).join(" ");
    const path=node("path",{d,class:"edge-line edge-"+info.kind,"marker-end":`url(#${markers[info.kind]})`,
      "data-edge-id":edgeId,"data-edge-kind":info.kind,...attributes});
    if(info.kind==="data")path.setAttribute("stroke-dasharray","7 5");
    group.append(path,node("path",{d,class:"edge-hit","data-edge-id":edgeId,"data-edge-kind":info.kind}));
    const hint=node("title",[info.label,info.facts.when?"条件："+info.facts.when:"",...info.lines].filter(Boolean).join("\n"));path.append(hint);
  }
  function drawBody(layout,offsetX=0,offsetY=0) {
    const group=node("svg",{width:layout.width,height:layout.height,viewBox:`0 0 ${layout.width} ${layout.height}`});
    const markers=arrows(group);
    const items=new Map(layout.values.map(v=>[v.id,v]));
    layout.edges.forEach(edge=>{
      const index=Number(edge.id.slice(4)),facts=layout.facts[index],info=layout.edgeInfo[index],from=items.get(facts.from),to=items.get(facts.to);
      if(!from||!to)throw new Error("连边缺少节点");
      const edgeId="edge-"+(++sequence);info.sourcePath=from.path;info.targetPath=to.path;getEdgeFacts().set(edgeId,info);
      for(const section of edge.sections||[]){
        const points=[section.startPoint,...(section.bendPoints||[]),section.endPoint].map(p=>({...p}));
        points[0]=VFShapes.connection(from,points[1]);points[points.length-1]=VFShapes.connection(to,points[points.length-2]);
        connection(group,points,info,edgeId,markers,{"data-from":from.path,"data-to":to.path});
      }
      const position=edge.labels?.[0];
      if(info.labelLines.length&&position){const g=node("g",{"data-edge-id":edgeId,"data-edge-kind":info.kind});g.append(node("rect",{x:position.x,y:position.y,width:position.width,height:position.height,class:"edge-label-background"}));
        info.labelLines.forEach((line,i)=>g.append(node("text",{x:position.x+8,y:position.y+19+i*18,class:"edge-label"},line)));group.append(g);}
    });
    for(const item of layout.values){
      const attributes={transform:`translate(${item.x},${item.y})`};attributes[layout.entity==="resource"?"data-resource-id":"data-call-path"]=item.path;
      const g=node("g",attributes);getVisible().set(item.path,{...item,x:item.x+offsetX,y:item.y+offsetY});
      if(item.inner){
        const values=item.card.values;
        g.append(node("rect",{width:item.width,height:item.height,class:"call-boundary",style:`fill:${values.fill||"#ece7d8"};stroke:${values.stroke||"#56534a"}`}));
        const header=node("g",{class:"group-header"});
        header.append(node("rect",{width:item.width,height:item.header.height,fill:values.fill||"#f3efe3"}));
        for(const row of item.header.rows)header.append(node("text",{x:20,y:row.y,class:"card-"+row.kind,fill:values.text||"#24231f"},row.text));
        header.append(node("path",{d:`M0 ${item.header.height} H${item.width}`,stroke:values.stroke||"#56534a"}));
        g.append(header);
        const x=(item.width-item.inner.width)/2,y=item.header.height+20;
        const inside=drawBody(item.inner,offsetX+item.x+x,offsetY+item.y+y);inside.setAttribute("transform",`translate(${x},${y})`);g.append(inside);}
      else g.append(VFShapes.draw(item.card,item.facts));
      group.append(g);
    }
    return group;
  }
  async function drawFlow(descriptor,token) {
    const data=getData(),mode=getMode();
    const body=data.bodies.workflow;if(!body)throw new Error("缺少流程数据");
    if(mode==="original"){
      if(!data.artifacts?.svg)throw new Error("本记录没有原 SVG 附件。使用 review --with-svg 生成对照。");
      const url=resourceUrl("snapshots/"+encodeURIComponent(getCurrent())+"/"+data.artifacts.svg),picture=new Image();
      await new Promise((resolve,reject)=>{picture.onload=resolve;picture.onerror=()=>reject(new Error("SVG 附件无法加载"));picture.src=url;});
      if(!isCurrent(token))return null;
      const wrapper=node("svg",{width:picture.naturalWidth||1200,height:picture.naturalHeight||800,viewBox:`0 0 ${picture.naturalWidth||1200} ${picture.naturalHeight||800}`});
      wrapper.append(node("image",{href:url,width:picture.naturalWidth||1200,height:picture.naturalHeight||800,"pointer-events":"none"}));return wrapper;
    }
    if(!factsNodes(body).length){empty(body.error||"当前 workflow 没有可显示节点。");return null;}
    const layout=await layoutBody("workflow");if(!isCurrent(token))return null;return drawBody(layout);
  }
  async function cards(values,relations,token) {
    if(!elk)throw new Error("离线 ELK 布局资源缺失。");
    if(!values.length){empty("当前 workflow 没有此类资源的展示事实。");return null;}
    const ids=new Set(values.map(v=>v.id));
    const edges=relations.filter(e=>ids.has(e.from)&&ids.has(e.to));
    const layout=await elk.layout({id:"resources",layoutOptions:{"elk.algorithm":"layered","elk.direction":"RIGHT","elk.spacing.nodeNode":"45"},
      children:values.map(v=>({id:v.id,width:280,height:92})),edges:edges.map((e,i)=>({id:String(i),sources:[e.from],targets:[e.to]}))});
    if(!isCurrent(token))return null;
    const group=node("g"),markers=arrows(group);
    for(const edge of layout.edges||[])for(const s of edge.sections||[]){
      const facts=edges[Number(edge.id)],edgeId="relation-"+(++sequence),info=VFModel.edgeInfo(facts);info.key="relation/"+edge.id;getEdgeFacts().set(edgeId,info);
      const p=[s.startPoint,...(s.bendPoints||[]),s.endPoint];
      connection(group,p,info,edgeId,markers);
      if(facts.relation){const point=p[Math.floor(p.length/2)];group.append(node("text",{x:point.x+7,y:point.y-7,class:"edge-label","data-edge-id":edgeId},facts.relation));}
    }
    for(const item of layout.children) {
      const facts=values.find(v=>v.id===item.id),g=node("g",{transform:`translate(${item.x},${item.y})`,"data-resource-id":facts.id});
      g.append(node("rect",{width:item.width,height:item.height,class:"resource-card"}));
      [facts.display_name||facts.label||facts.resource_id||facts.id,facts.kind||"",facts.source?.path||facts.source?.ref||facts.path||""].forEach((text,i)=>g.append(node("text",{x:14,y:25+i*23,class:"resource-text"},String(text).slice(0,42))));
      group.append(g);
      getVisible().set(facts.id,{...item,facts});
    }
    return group;
  }
  async function drawResources(descriptor,token) {
    const data=getData(),mode=getMode();
    const implementation=data.architecture.implementation_graph||{},all=Object.entries(implementation.resources||{}).map(([id,facts])=>({...facts,resource_id:facts.id,id}));
    const kinds=new Set(descriptor.kinds),selected=all.filter(r=>kinds.has(r.kind));
    if(!selected.length){empty("当前 workflow 没有此类资源的展示事实。");return null;}
    const selectedIds=new Set(selected.map(v=>v.id)),relations=implementation.relations||[];
    const relatedIds=new Set(relations.filter(e=>selectedIds.has(e.from)||selectedIds.has(e.to)).flatMap(e=>[e.from,e.to]));
    const values=all.filter(v=>selectedIds.has(v.id)||relatedIds.has(v.id)),ids=new Set(values.map(v=>v.id));
    const source=data.bodies.resources;if(!source)throw new Error("缺少资源事实。");
    const indexes=(source.facts.edges||[]).map((e,i)=>i).filter(i=>ids.has(source.facts.edges[i].from)&&ids.has(source.facts.edges[i].to));
    const body={...source,facts:{nodes:values,edges:indexes.map(i=>source.facts.edges[i])}};
    const layout=await layoutBody("resources","",[],body,"resource");if(!isCurrent(token))return null;return drawBody(layout);
  }
  async function drawLinks(descriptor,token) {
    const data=getData(),mode=getMode();
    const links=data.links||[],values=new Map();
    for(const link of links) {
      const from=link.from_root+":"+link.from_workflow,to=link.to_root+":"+link.to_workflow;
      values.set(from,{id:from,kind:"workflow",path:link.from_workflow,workflow_root:link.from_root,workflow_path:link.from_workflow});values.set(to,{id:to,kind:"workflow",path:link.to_workflow,workflow_root:link.to_root,workflow_path:link.to_workflow});
    }
    if(!links.length){empty("没有显式 workflow 关联声明。");return null;}
    const result=await cards([...values.values()],links.map(l=>({...l,from:l.from_root+":"+l.from_workflow,to:l.to_root+":"+l.to_workflow,relation:[l.kind,l.label||l.from_call_path].filter(Boolean).join(" · ")})),token);
    if(!isCurrent(token))return null;
    showInfo("显式 workflow 关联",{links,说明:"声明仅用于展示；不推断调度关系或真实父子运行。"});
    return result;
  }
  return {drawFlow,drawResources,drawLinks};
};
