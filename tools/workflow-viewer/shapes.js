/* Native, content-sized diagram cards. No imported SVG or Mermaid geometry. */
"use strict";
window.VFShapes=(()=>{
  const ns="http://www.w3.org/2000/svg";
  const node=(tag,attrs={},text=null)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==null)e.textContent=text;return e;};
  const supported=new Set(["rect","rounded","stadium","circle","dbl-circ","diam","diamond","lean-r","lean-l","trap-b","hex","fr-rect","cyl","doc","cloud"]);
  const canvas=document.createElement("canvas"),context=canvas.getContext("2d");
  function width(text,size=13){context.font=`${size}px Arial, sans-serif`;return context.measureText(String(text)).width;}
  function wrap(text,max=260,size=13){
    const lines=[];let line="";
    for(const character of String(text||"")){if(character==="\n"||width(line+character,size)>max){lines.push(line);line="";}if(character!=="\n")line+=character;}
    if(line)lines.push(line);return lines.length?lines:[""];
  }
  function measure(facts,types={},nodesets={}) {
    const descriptor=types[facts.type_used]||{},external=Boolean(descriptor.external||descriptor.info?.external);
    const values=facts.presentation?.values||facts.effective_presentation?.values||{};
    const requested=values.shape||"rect",shape=requested==="diamond"?"diam":supported.has(requested)?requested:"rect";
    const title=facts.role?.display_name||facts.display_name||facts.info?.display_name||facts.resource_id||facts.id;
    const titleLines=wrap(title,260,16),typeLines=wrap(facts.type_used||facts.kind||"",260,12);
    const contract=(facts.requires?.length||0)+" 输入 · "+(facts.provides?.length||0)+" 输出";
    const status=facts.status||"implemented";
    const rows=[...titleLines.map(t=>({text:t,kind:"title"})),...typeLines.map(t=>({text:t,kind:"type"})),
      {text:status==="planned"?"计划 · 尚未实现":external?"外部依赖":facts.invokes?"可展开 · "+(facts.invokes.kind==="loop_body"?"Loop":"Nodeset"):facts.flow_kind||facts.kind||"资源",kind:"status"},
      {text:facts.type_used?contract:(facts.sources?.length?facts.sources.length+" 个来源":""),kind:"detail"}];
    const description=VFModel.nodeInfo(facts,{node_types:types,nodesets}).description;
    if(description){const brief=wrap(description,260,12);rows.splice(titleLines.length+typeLines.length,0,...brief.slice(0,2).map((t,i)=>({text:t+(i===1&&brief.length>2?"…":""),kind:"description"})));}
    if(!supported.has(requested))rows.push({text:"未支持形状: "+requested,kind:"detail"});
    const contentWidth=Math.max(190,...rows.map(r=>width(r.text,r.kind==="title"?16:12)))+44,contentHeight=rows.length*23+24+(values.icon?24:0);
    let w=contentWidth,h=contentHeight;
    if(shape==="circle"||shape==="dbl-circ")w=h=Math.ceil(Math.hypot(w,h))+24;
    else if(shape==="diam"){w*=2;h*=2;}
    else if(shape==="stadium")w+=h;
    else if(["hex","lean-r","lean-l","trap-b"].includes(shape))w+=68;
    else if(shape==="cloud"){w+=58;h+=36;}
    else if(shape==="cyl")h+=64;
    else if(shape==="doc")h+=32;
    return {width:Math.ceil(w),height:Math.ceil(h),shape,requested,values,rows,contentHeight};
  }
  function outline(shape,w,h){
    const polygon=points=>node("polygon",{points});
    if(shape==="circle"||shape==="dbl-circ")return node("ellipse",{cx:w/2,cy:h/2,rx:w/2,ry:h/2});
    if(shape==="diam")return polygon(`${w/2},0 ${w},${h/2} ${w/2},${h} 0,${h/2}`);
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
    const shell=outline(shape,w,h);shell.setAttribute("class","card-outline");shell.setAttribute("fill",values.fill||"#f3efe3");shell.setAttribute("stroke",values.stroke||"#24231f");shell.setAttribute("stroke-width",2);g.append(shell);
    if(shape==="dbl-circ")g.append(node("ellipse",{cx:w/2,cy:h/2,rx:w/2-7,ry:h/2-7,fill:"none",stroke:values.stroke||"#24231f","stroke-width":1.5}));
    if(shape==="fr-rect")for(const x of [9,w-9])g.append(node("path",{d:`M${x} 0 V${h}`,stroke:values.stroke||"#24231f","stroke-width":1.5}));
    const top=(h-card.contentHeight)/2+24+(values.icon?24:0);
    card.rows.forEach((row,i)=>g.append(node("text",{x:w/2,y:top+i*23,"text-anchor":"middle",fill:values.text||"#24231f",class:"card-"+row.kind},row.text)));
    if(values.icon){const label=String(values.icon),fa=label.match(/(?:fa[bsr]?\s+)?fa-([\w-]+)/);if(fa){const f=node("foreignObject",{x:w/2-12,y:Math.max(2,top-42),width:24,height:24});const div=document.createElementNS("http://www.w3.org/1999/xhtml","div");const family=/\b(fab|fa-brands)\b/.test(label)?"fa-brands":/\b(far|fa-regular)\b/.test(label)?"fa-regular":"fa-solid";div.className=family+" fa-"+fa[1];div.style.color=values.text||"#24231f";f.append(div);g.append(f);}else g.append(node("text",{x:w/2,y:Math.max(22,top-23),"text-anchor":"middle",fill:values.text||"#24231f",class:"card-icon"},label));}
    return g;
  }
  function connection(item,toward){
    const w=item.width,h=item.height,c={x:item.x+w/2,y:item.y+h/2},dx=toward.x-c.x,dy=toward.y-c.y;
    const shape=item.inner?"rect":item.card.shape;
    let t=1/Math.max(Math.abs(dx)/(w/2),Math.abs(dy)/(h/2),1e-12);
    if(shape==="circle"||shape==="dbl-circ")t=1/Math.max(Math.hypot(dx/(w/2),dy/(h/2)),1e-12);
    if(shape==="diam")t=1/Math.max(Math.abs(dx)/(w/2)+Math.abs(dy)/(h/2),1e-12);
    if(["hex","lean-r","lean-l","trap-b"].includes(shape)){
      const points=shape==="hex"?[[30,0],[w-30,0],[w,h/2],[w-30,h],[30,h],[0,h/2]]:shape==="lean-r"?[[28,0],[w,0],[w-28,h],[0,h]]:shape==="lean-l"?[[0,0],[w-28,0],[w,h],[28,h]]:[[28,0],[w-28,0],[w,h],[0,h]];
      for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length],sx=b[0]-a[0],sy=b[1]-a[1],cross=dx*sy-dy*sx;if(Math.abs(cross)<1e-9)continue;const ax=a[0]-w/2,ay=a[1]-h/2,r=(ax*sy-ay*sx)/cross,u=(ax*dy-ay*dx)/cross;if(r>=0&&u>=0&&u<=1)t=Math.min(t,r);}
    }
    // Curved decorative outlines expose designed ports inset from the bounding box.
    if(shape==="cloud")t*=0.91;
    if(shape==="doc"&&dy>0)t*=0.85;
    if(shape==="cyl"&&Math.abs(dy)>Math.abs(dx))t*=0.98;
    return {x:c.x+t*dx,y:c.y+t*dy};
  }
  return {node,measure,draw,connection,width,wrap};
})();
