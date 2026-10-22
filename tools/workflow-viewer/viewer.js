/* Offline preview protocol v4. No fetch, server, source execution or directory enumeration. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let project = null;
  const collapsedRoots=new Set();
  let records = new Map(), currentRecord = null, refreshGeneration = 0;
  const snapshots = new Map(), states = new Map(), modes = new Map(), entries = new Map();
  let entry="";
  const ns = "http://www.w3.org/2000/svg", elk = typeof ELK === "undefined" ? null : new ELK();
  const configured=window.VibeFlowViewerConfig;
  const dataRoot=configured?.dataRoot?new URL(configured.dataRoot,$("viewer-config")?.src||document.baseURI):null;
  if(dataRoot&&!dataRoot.pathname.endsWith("/"))dataRoot.pathname+="/";
  const resourceUrl=path=>{if(!dataRoot)throw new Error("缺少 dataRoot 配置");return new URL(path,dataRoot).href;};
  let activeWorkflow="";
  const entryKey=()=>current+"|"+activeWorkflow;
  let current = null, data = null, view = "flow", mode = "structured", generation = 0;
  let state = null, visible = new Map(), edgeFacts = new Map(), contextPath = null, sequence = 0;
  const categoryNames = {review:"审查",build:"构建",run:"运行"};
  const statusNames = {passed:"审查通过",reviewing:"审查中 / 未记录结束",succeeded:"成功",running:"运行中 / 未记录结束",building:"构建中 / 未记录结束",failed:"失败",preview_failed:"预览生成失败"};
  const statusText = record => (record.status==="succeeded"?(categoryNames[record.category]||"")+"成功":statusNames[record.status]||record.status)+(record.check_status==="CONCERNS"?"（有关注项）":"");
  const {drawFlow,drawResources,drawLinks}=VFViews({getData:()=>data,getMode:()=>mode,getCurrent:()=>current,
    getEntry:()=>entry,
    getVisible:()=>visible,getEdgeFacts:()=>edgeFacts,isCurrent:token=>token===generation,elk,node,layoutBody,factsNodes,empty,showInfo,resourceUrl});
  const renderers = new Map([["flow", drawFlow], ["resources", drawResources], ["links", drawLinks]]);
  window.VibeFlowPreview = {
    record(value) {
      const target=document.currentScript?.previewRecords||records,prior=target.get(value.id);
      if(!prior||(value.revision||0)>=(prior.revision||0))target.set(value.id,value);
    },
    project(value) {
      if(value.version!==4||value.architecture&&value.architecture.format!=="vibeflow.project-architecture.v2")value={roots:[],error:"旧版项目目录；运行 preview --workspace 重新生成。"};
      const target=document.currentScript?.previewRecords;if(target)target.project=value;else project=value;
    },
    snapshot(value) { if(value.version!==4)throw new Error("不支持旧快照格式；请重新生成");snapshots.set(value.id,value); },
    // The renderer registry also permits future view kinds without changing the tab bar.
    registerRenderer(name, renderer) { renderers.set(name, renderer); }
  };
  function node(tag, attributes={}, text=null) {
    const value = document.createElementNS(ns, tag);
    for(const [key,item] of Object.entries(attributes)) value.setAttribute(key,item);
    if(text !== null) value.textContent=text;
    return value;
  }
  function notice(message="") { $("notice").textContent=message; }
  function empty(message) { $("empty").textContent=message; $("empty").hidden=!message; }
  const loadScript=VFModel.loadScript;
  function compareTime(a,b) {
    a=a||"";b=b||"";
    const milliseconds=Date.parse(a)-Date.parse(b);if(milliseconds)return milliseconds;
    const fraction=value=>(value.match(/\.(\d+)/)?.[1]||"").padEnd(6,"0").slice(0,6);
    const left=fraction(a),right=fraction(b);return left<right?-1:left>right?1:0;
  }
  function sortedRecords() { return [...records.values()].sort((a,b)=>compareTime(b.created_at,a.created_at)||b.id.localeCompare(a.id)); }
  function optionList(id, values, label) {
    const select=$(id), prior=select.value;
    select.replaceChildren(new Option(label,""), ...[...values].map(([key,text])=>new Option(text,key)));
    select.value=values.has(prior)?prior:"";
  }
  const dateText=value=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString():"未知";
  function recordButton(r,latest=false) {
    const button=document.createElement("button");button.className="record"+(r.id===current?" active":"");button.dataset.status=r.status;button.dataset.recordId=r.id;
    const badge=document.createElement("span");badge.className="badge";badge.textContent=(latest?"最新 · ":"")+(categoryNames[r.category]||r.category);
    const title=document.createElement("strong");title.textContent=r.workflow.name||r.workflow.path;
    const info=document.createElement("small");info.textContent=(latest?r.workflow.path+"\n更新于 "+dateText(r.updated_at||r.created_at):dateText(r.created_at)+"\n"+r.workflow.root_id)+" · "+r.workflow.target+(r.entry?" · 入口 "+r.entry:"")+" · "+statusText(r)+(r.preview_error?" · 预览不可用":"");
    button.append(badge,title,info);button.onclick=()=>navigate(r.id,"flow");return button;
  }
  function projectHistory() {
    const roots=new Map((project?.roots||[]).map(root=>[root.id,{...root,workflows:new Map(root.workflows.map(w=>[w.id,{...w}]))}]));
    for(const record of sortedRecords()){
      const w=record.workflow;
      const item=roots.get(w.root_id)?.workflows.get(w.id);
      if(item&&!item.latest)item.latest=record;
    }
    const groups=[];let count=0;
    for(const root of roots.values()){
      const group=document.createElement("details");group.className="project-root";group.dataset.rootId=root.id;group.open=!collapsedRoots.has(root.id);
      group.ontoggle=()=>group.open?collapsedRoots.delete(root.id):collapsedRoots.add(root.id);
      const summary=document.createElement("summary");summary.textContent=root.id+" · "+(root.target||"")+" · "+root.workflows.size+" workflow";group.append(summary);
      for(const w of [...root.workflows.values()].sort((a,b)=>a.path.localeCompare(b.path))){
        count++;const button=w.latest?recordButton(w.latest,true):document.createElement("button");
        if(w.latest)button.querySelector("strong").textContent=w.name||w.path;
        button.dataset.workflowId=w.id;
        if(!w.latest){button.className="record unavailable";button.disabled=true;
          const title=document.createElement("strong");title.textContent=w.name||w.path;
          const info=document.createElement("small");info.textContent=w.path+"\n"+(w.error?"配置有误 · "+w.error:"尚未生成审核图")+"\n源文件更新于 "+dateText(w.source_updated_at);button.append(title,info);
        }else if(w.error){const warning=document.createElement("small");warning.className="directory-warning";warning.textContent="当前配置有误；显示已有快照";button.append(warning);}
        group.append(button);
      }
      if(!root.workflows.size){const empty=document.createElement("p");empty.className="directory-empty";empty.textContent="暂无 workflow";group.append(empty);}
      groups.push(group);
    }
    $("count").textContent=roots.size+" root / "+count;
    $("project-note").textContent=project?.error||(project?(project.name+" · 各注册 root 的 workflow · 每个 workflow 的最新快照"+(project.inventory_complete?"":" · 部分配置有误")):"缺少项目目录；运行 preview --workspace 更新目录，或切换历史记录查看已有快照。");
    $("records").replaceChildren(...groups);
    if(!groups.length)$("records").textContent="尚无项目目录。";
  }
  function history() {
    const directory=$("navigation").value==="project";
    $("filters").hidden=directory;$("project-note").hidden=!directory;
    if(directory){projectHistory();return;}
    optionList("workflow",new Map(sortedRecords().map(r=>[r.workflow.id,r.workflow.root_id+" / "+r.workflow.path])),"全部 workflow");
    optionList("status",new Map(sortedRecords().map(r=>[r.status,statusNames[r.status]||r.status])),"全部状态");
    const filtered=sortedRecords().filter(r=>(!$("category").value||r.category===$("category").value)&&
      (!$("workflow").value||r.workflow.id===$("workflow").value)&&(!$("target").value||r.workflow.target===$("target").value)&&
      (!$("status").value||r.status===$("status").value));
    $("count").textContent=filtered.length+" / "+records.size;
    $("records").replaceChildren(...filtered.map(r=>recordButton(r)));
  }

  async function refresh(initial=false) {
    const ticket=++refreshGeneration,next=new Map();
    try {
      await loadScript(resourceUrl("project.js"),next).catch(()=>{});
      await loadScript(resourceUrl("index.js"),next);if(ticket!==refreshGeneration)return;
      project=next.project||null;records=next;history();VFOverview(project,sortedRecords(),navigate);notice();
      if(initial) {
        const hash=readHash();
        if(hash.snapshot)await open(hash.snapshot,hash.view||"flow",hash.call,hash.entry,hash.workflow);
        else if(records.size)await navigate(sortedRecords()[0].id,"flow");
      }else if(current){
        const record=records.get(current);
        if(record){
          currentRecord=record;$("identity").textContent=record.workflow.name+" · "+statusText(record);
          notice(record.preview_error||record.svg_error||"");
          if(!data&&record.views.length)await open(current,view,readHash().call);
          else if(data){
            const previous=data.artifacts?.svg;
            data={...data,artifacts:{...data.artifacts,...record.artifacts}};
            if(previous!==data.artifacts.svg&&mode==="original"&&data.views.find(v=>v.id===view)?.renderer==="flow")await draw();
          }
        }else if(data)notice("当前记录不在索引中；保留已加载的视图。");
      }
    }catch(error){if(ticket===refreshGeneration)notice(error.message+"；可用 preview --reindex 重建索引。");}
  }
  function readHash(){return Object.fromEntries(new URLSearchParams(location.hash.slice(1)));}
  function writeHash(call="") {
    const params=new URLSearchParams({snapshot:current,workflow:data?.workflow.id||records.get(current)?.workflow.id||"",view});
    if(call)params.set("call",call);
    if(entry)params.set("entry",entry);
    const hash="#"+params.toString();if(location.hash!==hash) window.history.pushState(null,"",hash);
  }
  async function navigate(id,tab,call="",targetWorkflow=id===current?activeWorkflow:"",targetEntry=undefined) { await open(id,tab,call,targetEntry,targetWorkflow);if(current===id&&records.has(id))writeHash(call); }
  async function open(id,tab="flow",call="",selectedEntry=undefined,workflowId="") {
    const token=++generation;
    current=id;activeWorkflow=workflowId||records.get(id)?.workflow.id||"";view=tab;entry=selectedEntry??entries.get(entryKey())??(activeWorkflow===records.get(id)?.workflow.id?records.get(id)?.entry:"")??"";entries.set(entryKey(),entry);mode=modes.get(entryKey())||"structured";data=null;state=null;visible=new Map();$("tabs").replaceChildren();$("scene").replaceChildren();$("dimensions").textContent="";history();empty("正在加载快照…");
    try {
      const record=records.get(id);
      if(!record)throw new Error("索引中没有此快照："+id);
      currentRecord=record;$("identity").textContent=record.workflow.name+" · "+statusText(record);notice(record.preview_error||record.svg_error||"");showInfo(record.workflow.name,{workflow:record.workflow,operation:record});
      if(record.preview_error&&!record.views.length)throw new Error(record.preview_error);
      if(!record.views.length&&["running","building","reviewing"].includes(record.status))throw new Error("预览正在生成；稍后刷新历史。");
      if(!snapshots.has(id))await loadScript(resourceUrl("snapshots/"+encodeURIComponent(id)+"/snapshot.js"));
      if(token!==generation)return;
      const snapshot=snapshots.get(id);if(!snapshot)throw new Error("快照未注册："+id);
      const graphs={...snapshot.workflow_graphs,[snapshot.workflow.id]:{workflow:snapshot.workflow,architecture:snapshot.architecture}};
      const chosen=graphs[activeWorkflow];if(!chosen?.architecture)throw new Error(chosen?.error||"本次快照中没有目标 workflow");
      data={...snapshot,workflow:chosen.workflow,architecture:chosen.architecture,workflow_graphs:graphs,
        artifacts:activeWorkflow===snapshot.workflow.id?{...snapshot.artifacts,...record.artifacts}:{},
        bodies:VFModel.bodies(chosen.architecture,chosen.workflow)};
      if(activeWorkflow!==snapshot.workflow.id)mode="structured";
      const named=data.architecture.workflow?.entries||{};
      if(entry&&!named[entry]){entry="";entries.set(entryKey(),entry);}
      $("entry").replaceChildren(new Option("全部入口",""),...Object.keys(named).map(name=>new Option(name+(name===data.architecture.workflow.default_entry?"（默认）":""),name)));$("entry").value=entry;
      $("identity").textContent=(data.workflow.name||data.workflow.path)+" · "+statusText(record);
      if(!data.views.some(v=>v.id===view))view=data.views[0]?.id;
      const remembered=states.has(stateKey());
      tabs();showInfo(data.workflow.name,{workflow:data.workflow,operation:record});if(!await draw())return;
      if(call&&(!remembered||state?.selected!==call))await locate(call);
      else if(state?.selectedEdge){const edge=[...edgeFacts.values()].find(e=>e.key===state.selectedEdge);if(edge)showInfo(edge.label,edge.facts,"",edge);}
      else if(state?.selected&&visible.has(state.selected)){const item=visible.get(state.selected);showInfo(item.facts.id||state.selected,item.facts,state.selected);}
    }catch(error){if(token===generation){$("scene").replaceChildren();empty(error.message);notice("其他历史记录仍可查看。");}}
  }
  function tabs() {
    $("tabs").replaceChildren(...data.views.map(item=>{
      const button=document.createElement("button");button.textContent=item.label;button.className=item.id===view?"active":"";
      button.onclick=()=>navigate(current,item.id);return button;
    }));
  }
  function stateKey(){return current+"|"+activeWorkflow+"|"+view+"|"+entry+"|"+(data.views.find(v=>v.id===view)?.renderer==="flow"?mode:"single");}
  function getState() {
    const key=stateKey();
    if(!states.has(key))states.set(key,{x:0,y:0,k:1,expanded:new Set(),selected:"",fitted:false});
    return states.get(key);
  }
  function transform() {
    $("scene").setAttribute("transform",`translate(${state.x},${state.y}) scale(${state.k})`);
    $("zoom").value=Number((state.k*100).toPrecision(5))+"%";
  }
  async function draw(anchor=null) {
    if(!data)return;
    const token=++generation;
    state=getState();visible=new Map();edgeFacts=new Map();$("scene").replaceChildren();empty("");
    const descriptor=data.views.find(v=>v.id===view), renderer=renderers.get(descriptor?.renderer);
    $("legend").hidden=descriptor?.renderer!=="flow"||mode!=="structured";
    $("mode").disabled=descriptor?.renderer!=="flow";$("mode").value=descriptor?.renderer==="flow"?mode:"structured";
    $("entry").disabled=descriptor?.renderer!=="flow"||mode!=="structured";
    $("collapse").disabled=descriptor?.renderer!=="flow"||mode!=="structured";
    try {
      if(!renderer)throw new Error("缺少此视图的渲染器："+descriptor?.renderer);
      const result=await renderer(descriptor,token);
      if(token!==generation)return;
      if(result)$("scene").append(result);
      if(anchor&&visible.has(anchor.path)) {
        const item=visible.get(anchor.path);state.x=anchor.x-(item.x+item.width/2)*state.k;
        state.y=anchor.y-(item.y+item.height/2)*state.k;
      }
      transform();if(!state.fitted){fit();state.fitted=true;}
      selection();$("dimensions").textContent=visible.size?visible.size+" 个可见对象":"";
      return true;
    }catch(error){if(token===generation)empty("此视图无法加载："+error.message);}
  }
  function invocationKey(facts) {return "nodeset:"+facts.invokes.target;}
  function expandable(facts) {return Boolean(facts.preview_expandable||VFModel.nodeInfo(facts,data.architecture).expandable);}
  function factsNodes(body) {return Array.isArray(body.facts.nodes)?body.facts.nodes:Object.values(body.facts.nodes||{});}
  function layoutBody(...args){return VFLayout.body({data,state,elk},...args);}
  function historyButton(label,root,path,call="") {
    const prepared=data?.workflow_graphs?.[root+":"+path];
    if(prepared?.error){const button=document.createElement("button");button.textContent=label+" → "+root+"/"+path+" · 本次目标不可用";button.disabled=true;button.title=prepared.error;return button;}
    if(prepared?.architecture){
      const button=document.createElement("button");button.textContent=label+" → "+root+"/"+path+" · 本次快照";
      button.onclick=()=>navigate(current,"flow",call,prepared.workflow.id,"");return button;
    }
    const target=sortedRecords().filter(r=>r.workflow.root_id===root&&r.workflow.path===path&&compareTime(r.created_at,currentRecord.created_at)<=0)[0];
    const button=document.createElement("button");
    button.textContent=label+" → "+root+"/"+path+(target?" · "+new Date(target.created_at).toLocaleString()+" · "+categoryNames[target.category]:" · 无同期历史快照");
    button.onclick=()=>target?navigate(target.id,"flow",call):showInfo("目标暂无历史快照",{root,path});return button;
  }
  function workflowButton(option){
    const button=document.createElement("button");button.textContent="跳转 → "+option.label;
    const target=data.workflow_graphs?.[option.id];const named=target?.architecture?.workflow?.entries||{};
    const error=option.error||(!target?.architecture?"本次快照没有目标事实":option.entry&&!named[option.entry]?"目标入口不存在":"");
    button.disabled=Boolean(error);button.title=error;
    button.onclick=()=>{$("context-menu").hidden=true;navigate(current,"flow","",option.id,option.entry);};
    return button;
  }
  function showInfo(title,facts,call="",edge=null) {
    $("details").replaceChildren();const heading=document.createElement("h3");heading.textContent=title;$("details").append(heading);
    if(call){const p=document.createElement("p");p.textContent="调用路径："+call;$("details").append(p);}
    if(facts?.invokes&&data?.bodies[invocationKey(facts)]?.error){
      const p=document.createElement("p");p.textContent="内部视图不可用："+data.bodies[invocationKey(facts)].error;$("details").append(p);
    }
    if(facts?.workflow_root)$("details").append(historyButton("查看 workflow",facts.workflow_root,facts.workflow_path));
    if(facts?.from_workflow&&facts?.to_workflow){
      $("details").append(historyButton("来源",facts.from_root,facts.from_workflow,facts.from_call_path||""),historyButton("目标",facts.to_root,facts.to_workflow));
    }
    const relevant=(data?.links||[]).filter(l=>(l.from_root===data.workflow.root_id&&l.from_workflow===data.workflow.path&&(!l.from_call_path||l.from_call_path===call))||
      l.to_root===data.workflow.root_id&&l.to_workflow===data.workflow.path);
    const related=document.createElement("details"),relatedTitle=document.createElement("summary");relatedTitle.textContent="workflow 关联（"+relevant.length+"）";related.append(relatedTitle);
    for(const link of relevant){
      const outgoing=link.from_root===data.workflow.root_id&&link.from_workflow===data.workflow.path;
      related.append(historyButton((outgoing?"":"来源 · ")+(link.label||link.kind),outgoing?link.to_root:link.from_root,
        outgoing?link.to_workflow:link.from_workflow,outgoing?"":link.from_call_path||""));
    }
    const item=visible.get(call),architecture=item?.architecture||data?.architecture||{};
    if(item)for(const option of VFModel.workflowOptions(item.facts,item.architecture,item.localPath,data.workflow_graphs))$("details").append(workflowButton(option));
    $("details").append(VFInspector.render(facts,architecture,edge));
    if(relevant.length)$("details").append(related);
  }
  function selection() {
    $("scene").querySelectorAll(".selection-outline").forEach(e=>e.remove());
    $("scene").querySelectorAll(".edge-line").forEach(e=>e.classList.toggle("edge-selected",Boolean(state.selectedEdge&&edgeFacts.get(e.dataset.edgeId)?.key===state.selectedEdge)));
    const item=visible.get(state.selected);
    if(item)$("scene").append(node("rect",{x:item.x-5,y:item.y-5,width:item.width+10,height:item.height+10,class:"selection-outline"}));
  }
  function select(path) {
    state.selectedEdge="";state.selected=path;selection();const item=visible.get(path);
    if(item)showInfo(item.facts.id||path,item.facts,path);
    else {const f=factsNodes(data.bodies.workflow).find(n=>encodeURIComponent(n.id)===path);if(f)showInfo(path,f,path);}
    writeHash(path);
  }
  async function toggle(path) {
    const item=visible.get(path);if(!item||!expandable(item.facts))return;
    const anchor={path,x:state.x+(item.x+item.width/2)*state.k,y:state.y+(item.y+item.height/2)*state.k};
    state.expanded.has(path)?state.expanded.delete(path):state.expanded.add(path);
    if(await draw(anchor))select(path);
  }
  function fit() {
    if(!state||!$("scene").children.length)return;
    const box=$("scene").getBBox(),rect=$("viewport").getBoundingClientRect();
    if(box.width&&box.height){state.k=Math.min((rect.width-64)/box.width,(rect.height-64)/box.height);state.x=(rect.width-box.width*state.k)/2-box.x*state.k;state.y=(rect.height-box.height*state.k)/2-box.y*state.k;transform();}
  }
  function zoom(value,x=null,y=null) {
    if(!state||!Number.isFinite(value)||value<=0){notice("缩放比例必须是正数。");return;}
    const rect=$("viewport").getBoundingClientRect();x=x??rect.width/2;y=y??rect.height/2;
    state.x=x-(x-state.x)*value/state.k;state.y=y-(y-state.y)*value/state.k;state.k=value;transform();notice();
  }
  function findPath(query) {
    let best=null,score=Infinity;const lower=query.toLowerCase();
    if(visible.has(query))return {path:query,choices:[]};
    function visit(key,prefix="",ancestors=[],localPrefix=[],choices=[]){
      if(ancestors.includes(key)||!data.bodies[key])return;
      const body=data.bodies[key];
      for(const facts of factsNodes(body)){
        const segment=encodeURIComponent(facts.id),path=prefix?prefix+"/"+segment:segment;
        const localPath=[...localPrefix,facts.id];
        const rank=path===query?0:facts.id===query?1:facts.definition_id===query?2:
          path.toLowerCase()===lower||facts.id.toLowerCase()===lower?3:path.toLowerCase().includes(lower)?4:Infinity;
        if(rank<score){best={path,choices};score=rank;}
        for(const option of VFModel.childOptions(facts,body,localPath,data.bodies))if(!option.error){
          visit(option.key,path,ancestors.concat(key),localPath,choices);
        }
      }
    }
    visit(entry?"entry:"+encodeURIComponent(entry):"workflow");return best;
  }
  async function locate(query) {
    if(!query||!data)return;
    if(view!=="flow"){await navigate(current,"flow",query);return;}
    if(mode!=="structured"){mode="structured";modes.set(entryKey(),mode);$("mode").value=mode;state=getState();}
    const found=findPath(query);if(!found){notice("没有找到节点："+query);return;}
    const {path}=found;
    const parts=path.split("/");for(let i=1;i<parts.length;i++)state.expanded.add(parts.slice(0,i).join("/"));
    if(!await draw())return;const item=visible.get(path);if(!item)return;
    const rect=$("viewport").getBoundingClientRect();state.x=rect.width/2-(item.x+item.width/2)*state.k;state.y=rect.height/2-(item.y+item.height/2)*state.k;
    transform();select(path);notice();
  }
  let pointer=null,dragged=false;
  $("viewport").addEventListener("pointerdown",event=>{
    if(event.button!==0||!state)return;
    pointer={id:event.pointerId,x:event.clientX,y:event.clientY,tx:state.x,ty:state.y,path:event.target.closest("[data-call-path]")?.dataset.callPath,
      resource:event.target.closest("[data-resource-id]")?.dataset.resourceId,edge:event.target.closest("[data-edge-id]")?.dataset.edgeId};
    dragged=false;$("viewport").setPointerCapture(event.pointerId);
  });
  $("viewport").addEventListener("pointermove",event=>{
    if(!pointer||event.pointerId!==pointer.id)return;
    const dx=event.clientX-pointer.x,dy=event.clientY-pointer.y;
    if(Math.hypot(dx,dy)>3)dragged=true;
    if(dragged){state.x=pointer.tx+dx;state.y=pointer.ty+dy;transform();$("viewport").classList.add("dragging");}
  });
  $("viewport").addEventListener("pointerup",event=>{
    if(pointer&&!dragged&&pointer.path)select(pointer.path);
    if(pointer&&!dragged&&pointer.resource){const item=visible.get(pointer.resource);if(item){state.selectedEdge="";state.selected=pointer.resource;selection();showInfo(item.facts.resource_id||item.facts.id,item.facts);}}
    if(pointer&&!dragged&&pointer.edge){const info=edgeFacts.get(pointer.edge);if(info){state.selected="";state.selectedEdge=info.key;selection();showInfo(info.label,info.facts,"",info);writeHash();}}
    pointer=null;$("viewport").classList.remove("dragging");
  });
  $("viewport").addEventListener("pointercancel",()=>{pointer=null;$("viewport").classList.remove("dragging");});
  $("viewport").addEventListener("wheel",event=>{event.preventDefault();if(!state)return;const rect=$("viewport").getBoundingClientRect();zoom(state.k*Math.exp(-event.deltaY*.0015),event.clientX-rect.left,event.clientY-rect.top);},{passive:false});
  $("viewport").addEventListener("contextmenu",event=>{
    event.preventDefault();contextPath=event.target.closest("[data-call-path]")?.dataset.callPath;
    if(!contextPath)return;
    select(contextPath);const item=visible.get(contextPath),menu=$("context-menu");
    $("toggle").hidden=!item?.facts.invokes;$("toggle").disabled=mode!=="structured"||!item||!expandable(item.facts);$("toggle").textContent=state.expanded.has(contextPath)?"原地收起":"原地展开";
    const targets=item?VFModel.workflowOptions(item.facts,item.architecture,item.localPath,data.workflow_graphs):[];
    $("context-targets").replaceChildren(...targets.map(workflowButton));
    menu.hidden=false;menu.style.left=Math.min(event.clientX,innerWidth-175)+"px";menu.style.top=Math.min(event.clientY,innerHeight-100)+"px";
  });
  document.addEventListener("pointerdown",event=>{if(!event.target.closest("#context-menu"))$("context-menu").hidden=true;});
  $("toggle").onclick=()=>{const path=contextPath;$("context-menu").hidden=true;toggle(path);};
  $("locate").onclick=()=>{$("context-menu").hidden=true;locate(contextPath);};
  $("refresh").onclick=()=>refresh();for(const id of ["category","workflow","target","status","navigation"])$(id).onchange=history;
  $("mode").onchange=()=>{mode=$("mode").value;modes.set(entryKey(),mode);draw();};
  $("plus").onclick=()=>state&&zoom(state.k*1.25);$("minus").onclick=()=>state&&zoom(state.k/1.25);
  $("zoom").onchange=()=>zoom(Number($("zoom").value.replace(/%$/, ""))/100);
  $("actual").onclick=()=>zoom(1);$("fit").onclick=fit;
  $("collapse").onclick=()=>{state.expanded.clear();draw();};
  $("search-form").onsubmit=event=>{event.preventDefault();locate($("search").value.trim());};
  $("entry").onchange=()=>{entry=$("entry").value;entries.set(entryKey(),entry);writeHash();draw();};
  window.addEventListener("popstate",()=>{const h=readHash();if(h.snapshot)open(h.snapshot,h.view,h.call,h.entry||"",h.workflow);});
  refresh(true);
})();
