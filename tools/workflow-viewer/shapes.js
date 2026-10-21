/* Native, content-sized diagram cards. No imported SVG or Mermaid geometry. */
"use strict";
window.VFShapes=(()=>{
  const ns="http://www.w3.org/2000/svg";
  const node=(tag,attrs={},text=null)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==null)e.textContent=text;return e;};
  const supported=new Set(["rect","rounded","stadium","circle","dbl-circ","diamond","lean-r","lean-l","trap-b","hex","fr-rect","cyl","doc","cloud"]);
  const boundaries=new WeakMap();
  const canvas=document.createElement("canvas"),context=canvas.getContext("2d");
  function width(text,size=13){context.font=`${size}px Arial, sans-serif`;return context.measureText(String(text)).width;}
  function wrap(text,max=260,size=13){
    const lines=[];let line="";
    for(const character of String(text||"")){if(character==="\n"||width(line+character,size)>max){lines.push(line);line="";}if(character!=="\n")line+=character;}
    if(line)lines.push(line);return lines.length?lines:[""];
  }
  const title=facts=>facts.role?.display_name||facts.display_name||facts.info?.display_name||facts.resource_id||facts.id;
  function groupHeader(facts,architecture,w){
    const max=Math.min(w-40,640),description=VFModel.nodeInfo(facts,architecture).description;
    const rows=wrap(title(facts),max,16).map(text=>({text,kind:"title"}));
    if(description)rows.push(...wrap(description,max,12).map(text=>({text,kind:"description"})));
    let y=30;
    for(const row of rows){row.y=y;y+=row.kind==="title"?23:18;}
    return {rows,height:y+10};
  }
  const operationStyles={
    call:{shape:"fr-rect",fill:"#ede9fe",stroke:"#7c3aed",text:"#3b0764"},
    wait:{shape:"hex",fill:"#fef3c7",stroke:"#d97706",text:"#78350f"},
    send:{shape:"lean-r",fill:"#e0f2fe",stroke:"#0284c7",text:"#0c4a6e"},
    receive:{shape:"lean-l",fill:"#dcfce7",stroke:"#16a34a",text:"#14532d"},
    kill:{shape:"rounded",fill:"#ffe4e6",stroke:"#be123c",text:"#881337"},
    self:{shape:"circle",fill:"#e2e8f0",stroke:"#475569",text:"#1e293b"},
    multiple:{shape:"doc",fill:"#ccfbf1",stroke:"#0f766e",text:"#134e4a"}
  };
  function measure(facts,architecture={}) {
    const info=VFModel.nodeInfo(facts,architecture),external=Boolean(info.definitionInfo.external||facts.external||facts.info?.external);
    const presentation=facts.presentation?.values?facts.presentation:facts.effective_presentation||{},values={...presentation.values},sources={...presentation.sources};
    const operations=[...new Set((facts.preview_operations||[]).filter(a=>a.capability==="vibeflow.workflow"&&operationStyles[a.operation]).map(a=>a.operation))];
    const operation=operations.length>1?"multiple":operations[0],defaults=operationStyles[operation];
    if(defaults)for(const [key,value] of Object.entries(defaults)){
      if(!values[key]||sources[key]==="native"){values[key]=value;sources[key]="workflow 操作 · "+operation;}
    }
    const requested=values.shape||"rect",canonical=requested,shape=supported.has(canonical)?canonical:"rect";
    const titleLines=wrap(title(facts),260,16),typeLines=wrap(facts.definition_id||facts.kind||"",260,12);
    const contract=(facts.requires??info.contract.requires??[]).length+" 输入 · "+(facts.provides??info.contract.provides??[]).length+" 输出";
    const status=info.status;
    const rows=[...titleLines.map(t=>({text:t,kind:"title"})),...typeLines.map(t=>({text:t,kind:"type"})),
      {text:status==="planned"?"计划 · 尚未实现":external?"外部依赖":facts.invokes?(facts.invokes.kind==="loop_body"?"Loop":"Nodeset"):facts.flow_kind||facts.kind||"资源",kind:"status"},
      {text:facts.definition_id||facts.kind==="node"?contract:(facts.sources?.length?facts.sources.length+" 个来源":""),kind:"detail"}];
    if(facts.invokes)rows.push({text:info.expandable?"可右键展开内部结构":"暂无内部定义",kind:"detail"});
    for(const action of (facts.preview_operations||[]).slice(0,3))rows.push({text:VFModel.operationLabel(action)+(action.target?" · "+action.target:""),kind:"detail"});
    if(!facts.invokes&&facts.preview_expandable)rows.push({text:"双击或右键展开目标 workflow",kind:"detail"});
    const description=info.description;
    if(description){const brief=wrap(description,260,12);rows.splice(titleLines.length+typeLines.length,0,...brief.slice(0,2).map((t,i)=>({text:t+(i===1&&brief.length>2?"…":""),kind:"description"})));}
    if(!supported.has(canonical))rows.push({text:"未支持形状: "+requested,kind:"detail"});
    const contentWidth=Math.max(190,...rows.map(r=>width(r.text,r.kind==="title"?16:12)))+44,contentHeight=rows.length*23+24+(values.icon?24:0);
    let w=contentWidth,h=contentHeight;
    if(shape==="circle"||shape==="dbl-circ")w=h=Math.ceil(Math.hypot(w,h))+24;
    else if(shape==="diamond"){w*=2;h*=2;}
    else if(shape==="stadium")w+=h;
    else if(["hex","lean-r","lean-l","trap-b"].includes(shape))w+=68;
    else if(shape==="cloud"){w+=58;h+=36;}
    else if(shape==="cyl")h+=64;
    else if(shape==="doc")h+=32;
    return {width:Math.ceil(w),height:Math.ceil(h),shape,requested,values,rows,contentHeight,operation,presentation:{values,sources}};
  }
  function outline(shape,w,h){
    const polygon=points=>node("polygon",{points});
    if(shape==="circle"||shape==="dbl-circ")return node("ellipse",{cx:w/2,cy:h/2,rx:w/2,ry:h/2});
    if(shape==="diamond")return polygon(`${w/2},0 ${w},${h/2} ${w/2},${h} 0,${h/2}`);
    if(shape==="hex")return polygon(`30,0 ${w-30},0 ${w},${h/2} ${w-30},${h} 30,${h} 0,${h/2}`);
    if(shape==="lean-r")return polygon(`28,0 ${w},0 ${w-28},${h} 0,${h}`);
    if(shape==="lean-l")return polygon(`0,0 ${w-28},0 ${w},${h} 28,${h}`);
    if(shape==="trap-b")return polygon(`28,0 ${w-28},0 ${w},${h} 0,${h}`);
    if(shape==="cyl")return node("path",{d:`M0 20 C0 -6 ${w} -6 ${w} 20 L${w} ${h-20} C${w} ${h+6} 0 ${h+6} 0 ${h-20} Z M0 20 C0 46 ${w} 46 ${w} 20`});
    if(shape==="doc")return node("path",{d:`M0 0 H${w} V${h-16} C${w*.66} ${h-48} ${w*.33} ${h+16} 0 ${h-16} Z`});
    if(shape==="cloud")return node("path",{d:`M18 ${h*.38} C-8 ${h*.2} ${w*.12} 0 ${w*.28} 14 C${w*.36} -8 ${w*.6} -8 ${w*.68} 15 C${w*.9} -4 ${w+10} ${h*.12} ${w-16} ${h*.38} C${w+12} ${h*.53} ${w+4} ${h*.83} ${w-24} ${h*.84} C${w*.85} ${h+12} ${w*.63} ${h+8} ${w*.52} ${h-12} C${w*.35} ${h+12} ${w*.12} ${h+8} ${w*.12} ${h-16} C-8 ${h*.88} -10 ${h*.54} 18 ${h*.38} Z`});
    return node("rect",{width:w,height:h,rx:shape==="stadium"?h/2:shape==="rounded"?16:0});
  }
  function draw(card,facts){
    const {width:w,height:h,shape,values}=card,g=node("g",{"data-shape":card.requested,class:"node-card"});
    if(card.operation)g.dataset.workflowOperation=card.operation;
    const shell=outline(shape,w,h);shell.setAttribute("class","card-outline");shell.setAttribute("fill",values.fill||"#f3efe3");shell.setAttribute("stroke",values.stroke||"#24231f");shell.setAttribute("stroke-width",2);g.append(shell);
    if(shape==="dbl-circ")g.append(node("ellipse",{cx:w/2,cy:h/2,rx:w/2-7,ry:h/2-7,fill:"none",stroke:values.stroke||"#24231f","stroke-width":1.5}));
    if(shape==="fr-rect")for(const x of [9,w-9])g.append(node("path",{d:`M${x} 0 V${h}`,stroke:values.stroke||"#24231f","stroke-width":1.5}));
    const top=(h-card.contentHeight)/2+24+(values.icon?24:0);
    card.rows.forEach((row,i)=>g.append(node("text",{x:w/2,y:top+i*23,"text-anchor":"middle",fill:values.text||"#24231f",class:"card-"+row.kind},row.text)));
    if(values.icon){const label=String(values.icon),fa=label.match(/(?:fa[bsr]?\s+)?fa-([\w-]+)/);if(fa){const f=node("foreignObject",{x:w/2-12,y:Math.max(2,top-42),width:24,height:24});const div=document.createElementNS("http://www.w3.org/1999/xhtml","div");const family=/\b(fab|fa-brands)\b/.test(label)?"fa-brands":/\b(far|fa-regular)\b/.test(label)?"fa-regular":"fa-solid";div.className=family+" fa-"+fa[1];div.style.color=values.text||"#24231f";f.append(div);g.append(f);}else g.append(node("text",{x:w/2,y:Math.max(22,top-23),"text-anchor":"middle",fill:values.text||"#24231f",class:"card-icon"},label));}
    return g;
  }
  function boundary(item){
    if(boundaries.has(item))return boundaries.get(item);
    const shell=outline(item.inner?"rect":item.card.shape,item.width,item.height),path=new Path2D(shell.getAttribute("d")||"");
    const number=key=>Number(shell.getAttribute(key)||0);
    if(shell.tagName==="rect")path.roundRect(0,0,number("width"),number("height"),number("rx"));
    if(shell.tagName==="ellipse")path.ellipse(number("cx"),number("cy"),number("rx"),number("ry"),0,0,Math.PI*2);
    if(shell.tagName==="polygon"){
      const points=shell.getAttribute("points").trim().split(/[ ,]+/).map(Number);
      path.moveTo(points[0],points[1]);for(let i=2;i<points.length;i+=2)path.lineTo(points[i],points[i+1]);path.closePath();
    }
    boundaries.set(item,path);return path;
  }
  function connection(item,toward){
    const w=item.width,h=item.height,c={x:w/2,y:h/2},dx=toward.x-item.x-c.x,dy=toward.y-item.y-c.y,length=Math.hypot(dx,dy);
    if(!length)return {x:item.x+c.x,y:item.y+c.y};
    const path=boundary(item),ux=dx/length,uy=dy/length;
    let inside=0,outside=Math.hypot(w,h)*2;
    for(let i=0;i<32;i++){const d=(inside+outside)/2;if(context.isPointInPath(path,c.x+d*ux,c.y+d*uy))inside=d;else outside=d;}
    return {x:item.x+c.x+inside*ux,y:item.y+c.y+inside*uy};
  }
  return {node,measure,draw,connection,width,wrap,groupHeader};
})();
