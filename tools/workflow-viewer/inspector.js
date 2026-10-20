/* Readable details from a call and its associated declarations; no source loading. */
"use strict";
window.VFInspector=(()=>{
  const element=(tag,text=null)=>{const e=document.createElement(tag);if(text!==null)e.textContent=text;return e;};
  const text=value=>Array.isArray(value)&&value.every(v=>typeof v!=="object")?value.join(" · "):typeof value==="object"?JSON.stringify(value,null,2):String(value);
  const present=value=>value!==undefined&&value!==null&&value!=="";
  function table(parent,values){
    const dl=element("dl");dl.className="fact-summary";
    for(const [label,value] of values)if(present(value)){dl.append(element("dt",label),element("dd",text(value)));}
    if(dl.children.length)parent.append(dl);
  }
  function section(parent,title){const e=element("section");e.append(element("h4",title));parent.append(e);return e;}
  function notes(parent,values){for(const value of Array.isArray(values)?values:present(values)?[values]:[])parent.append(element("p",text(value)));}
  function source(value){
    if(!value)return "";
    return [value.root_id,value.path||value.ref||value.module,value.line?"行 "+value.line:"",value.class||value.export].filter(Boolean).join(" · ");
  }
  const values=value=>value?.values??value??{};
  const nonempty=value=>value&&Object.keys(value).length>0;
  function semantics(info,key){return info?.contract?.[key]||{};}
  function contracts(parent,title,items,meaning={},direction="input"){
    const part=section(parent,title);
    if(!items?.length){part.append(element("p","未声明"));return;}
    for(const item of items){
      const row=element("article");row.className="contract-detail";
      row.append(element("strong",item.display_name||item.key||item.id||item.type||"契约"));
      const names={key:"键",type:"类型",cardinality:"数量约束",as:"接收名称",from:"来源",required:"必需",description:"说明",nullable:"允许空值"};
      table(row,Object.entries(item).filter(([key])=>key!=="display_name").map(([key,value])=>[names[key]||key,value]));
      notes(row,meaning[direction==="output"?item.key:item.type]);part.append(row);
    }
  }
  function raw(parent,value){const d=element("details");d.append(element("summary","全部事实（含关联定义）"),element("pre",JSON.stringify(value,null,2)));parent.append(d);}
  function nodeDetails(parent,facts,architecture){
    const info=VFModel.nodeInfo(facts,architecture),type=info.type,definition=info.definition,t=info.typeInfo;
    table(parent,[["类型",facts.type_used||facts.kind],["状态",info.status],
      ["调用声明状态",facts.status!==info.status?facts.status:undefined],
      ["目标定义状态",definition?.status??facts.invokes?.target_status],
      ["内部结构",facts.invokes?(info.expandable?"可原地展开":"暂无内部定义"):undefined],["流程类型",facts.flow_kind||t.flow_kind],
      ["调用职责",facts.role?.description],["类型说明",t.description||facts.info?.description||facts.description],
      ["Nodeset 说明",definition?.description],["版本",t.version||facts.version],["作者",t.author||facts.author],
      ["标签",facts.tags?.length?facts.tags:t.tags?.length?t.tags:undefined],
      ["调用来源",source(facts.source)],["实现来源",source(type?.source)],["声明来源",source(type?.declaration)],
      ["实现入口",type?.implementations?.map(i=>[i.language,(i.targets||[]).join(" / "),source(i.source)].filter(Boolean).join(" · ")).join("\n")],
      ["定义来源",source(definition?.source)],["资源来源",facts.sources?.length?facts.sources.map(source).join("\n"):facts.path],
      ["目标定义",facts.invokes?.target],["汇合策略",facts.join_policy],["副作用范围",facts.effect_scope||type?.info?.effect_scope],
      ["执行锁",facts.effective_execution_lock||facts.execution_lock],
      ["BaseLib 依赖",type?.base_libs?.length?type.base_libs:info.resource?.base_libs?.length?info.resource.base_libs:undefined],
      ["能力要求",type?.capabilities?.length?type.capabilities:info.resource?.capabilities?.length?info.resource.capabilities:undefined]]);
    if(facts.type_used||facts.contract||facts.requires||facts.provides){
      contracts(parent,"输入契约",facts.requires??info.contract.requires??definition?.requires,semantics(info,"input_semantics"));
      contracts(parent,"输出契约",facts.provides??info.contract.provides??definition?.provides,semantics(info,"output_semantics"),"output");
    }
    const defaults=info.config.defaults||info.config.params_defaults||{},schema=info.config.schema||info.config.params_schema||{};
    const call=values(facts.config?.call),overrides=values(facts.config?.node_configs);
    if([defaults,schema,call,overrides].some(nonempty)){
      const part=section(parent,"参数与配置");
      for(const [title,value] of [["默认参数",defaults],["参数约束",schema],["调用参数",call],["内部节点覆盖",overrides]])
        if(nonempty(value)){part.append(element("h5",title));table(part,Object.entries(value));}
    }
    if(facts.loop){const part=section(parent,"Loop 规则");table(part,Object.entries(facts.loop));}
    if(facts.io){const part=section(parent,"IO 声明");table(part,Object.entries(facts.io));}
    if(facts.preview_operations?.length){
      const part=section(parent,"接口操作与等待行为");
      for(const action of facts.preview_operations){const row=element("article");row.className="contract-detail";
        row.append(element("strong",VFModel.operationLabel(action)));table(row,Object.entries(action).map(([key,value])=>[({capability:"Capability",target:"目标别名",entry:"目标入口",wait:"等待执行结束",operation:"操作"})[key]||key,value]));part.append(row);}
    }
    if(nonempty(definition?.global_config?.values??definition?.global_config)){const part=section(parent,"Nodeset 全局配置声明");table(part,Object.entries(values(definition.global_config)));}
    if(nonempty(facts.metadata)||nonempty(type?.metadata)){const part=section(parent,"补充元数据");table(part,[["调用",facts.metadata],["类型",type?.metadata]]);}
    const rules=facts.selected_rulesets??facts.rulesets??type?.rulesets;
    if(rules?.length){const part=section(parent,"规则声明");notes(part,rules);}
    if(info.plannedBehavior){const part=section(parent,"计划节点行为");table(part,Object.entries(info.plannedBehavior));}
    const p=facts.presentation?.values?facts.presentation:facts.effective_presentation;
    if(p){const part=section(parent,"展示样式");table(part,[["最终样式",p.values],["样式来源",p.sources]]);}
    raw(parent,{call:facts,...(type?{node_type:type}:{}),...(definition?{nodeset:definition}:{}),...(info.resource?{resource:info.resource}:{})});
  }
  function edgeDetails(parent,info){
    const facts=info.facts;
    table(parent,[["连边类型",info.label],["起点",info.sourcePath||facts.from],["终点",info.targetPath||facts.to],
      ["触发条件",facts.when||"无条件"],["边的角色",info.roleLabels.length?info.roleLabels.join(" · "):"未提供调度角色"],
      ["触发下游",info.roles.length?(info.scheduled?"是":"否"):undefined],["传递数据",info.roles.length?(info.transfer?"允许":"否"):undefined],
      ["关系",facts.relation]]);
    if(info.kind==="parallel")parent.append(element("p","此处标识可调度的分发 / 等待全部分支的汇合结构。实际执行仍受条件、并发限制和执行锁约束。"));
    const part=section(parent,"数据传递契约");
    if(!info.transfers.length)part.append(element("p",info.transfer?"未声明匹配的数据契约；不推断业务载荷。":"此边未声明数据传递。"));
    for(const {provider,requirement} of info.transfers){
      const row=element("article");row.className="contract-detail";
      row.append(element("strong",(provider.display_name||provider.key||provider.type)+" → "+(requirement.display_name||requirement.as||requirement.type)));
      table(row,[["数据类型",provider.type],["上游输出",provider],["下游输入",requirement]]);
      const output=semantics(info.sourceInfo,"output_semantics")[provider.key],input=semantics(info.targetInfo,"input_semantics")[requirement.type];
      if(output){row.append(element("h5","输出语义"));notes(row,output);}
      if(input){row.append(element("h5","输入语义"));notes(row,input);}
      part.append(row);
    }
    raw(parent,{edge:facts,...(info.sourceInfo?{source:info.sourceInfo}:{}),...(info.targetInfo?{target:info.targetInfo}:{})});
  }
  function render(facts,architecture={},edge=null){const fragment=document.createDocumentFragment();if(edge)edgeDetails(fragment,edge);else nodeDetails(fragment,facts,architecture);return fragment;}
  return {render};
})();
