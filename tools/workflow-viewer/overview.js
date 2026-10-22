/* Project overview is a projection of the exported PROJECT_ARCHITECTURE document. */
"use strict";
window.VFOverview=(project,records,navigate)=>{
  const root=document.getElementById("project-content");root.replaceChildren();
  const element=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
  const architecture=project?.architecture;
  if(!architecture){root.textContent=project?.error||"缺少 PROJECT_ARCHITECTURE.jsonc；运行 preview --workspace 更新。";return;}
  root.append(element("p",(architecture.purpose||project.name)+" · 总览更新于 "+new Date(project.updated_at).toLocaleString()+(!architecture.inventory_complete?" · 清单存在错误":"")));
  const table=rows=>{const t=element("table");for(const row of rows){const tr=element("tr");for(const text of row)tr.append(element("td",text));t.append(tr);}return t;};
  root.append(table([["目录","功能","身份"],...architecture.directories.map(d=>[d.path,d.purpose||"未声明",d.role+(d.root_ids?.length?" · "+d.root_ids.join("、"):"")])]));
  for(const owner of architecture.roots){
    const group=element("details");group.append(element("summary",owner.id+" · "+owner.path+" · "+owner.target+" · "+owner.workflows.length+" workflow"));
    group.append(element("p",owner.purpose||"未声明 root 用途"));
    group.append(table([["目录","功能"],...owner.directories.map(d=>[d.project_path,d.purpose||"未声明"])]));
    for(const workflow of owner.workflows){
      const item=element("article");item.append(element("strong",workflow.name+" · "+workflow.project_path));
      item.append(element("p",workflow.description||"未声明 workflow 用途"));
      item.append(element("p","入口："+(Object.keys(workflow.entries||{}).join("、")||"未命名")+(workflow.default_entry?" · 默认 "+workflow.default_entry:"")));
      item.append(element("p","Architecture："+(workflow.architecture?(workflow.architecture+(workflow.architecture_exists?"":" · 尚未生成")):"未登记")));
      const latest=records.find(record=>record.workflow.id===workflow.id);
      if(latest){const button=element("button","查看最新快照");button.onclick=()=>navigate(latest.id,"flow");item.append(button);}
      for(const relation of workflow.relations||[]){const ref=relation.workflow;item.append(element("p",relation.call_path.join("/")+" · "+relation.operation+" → "+ref.root+"/"+ref.path+(ref.entry?" · 入口 "+ref.entry:"")+(relation.expected?" · 预期交互":"")));}
      if(workflow.error)item.append(element("p","配置错误："+workflow.error));
      group.append(item);
    }
    root.append(group);
  }
  for(const issue of architecture.diagnostics||[])root.append(element("p",issue.path+" · "+issue.message));
};
