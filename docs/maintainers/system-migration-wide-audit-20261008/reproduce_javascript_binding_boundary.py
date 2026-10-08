import json, sys
from dataclasses import replace
from pathlib import Path
ROOT=Path('/home/rockingsisyphus/projects/VibeFlow');sys.path.insert(0,str(ROOT/'src'))
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest,prepare_project_build
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.bindings import build_javascript_binding_plan
existing=json.loads(Path('/tmp/vibeflow-wide-js-probe.json').read_text())
root=Path(existing['temporary_root']);project=root/'domain/project';p=prepare_project_build(ProjectBuildRequest(root/'domain/vibeflow_config.jsonc',project/'configs/model.jsonc',root/'binding-dist','node','single-esm'))
changed=replace(p.plan,blocks=tuple(replace(block,nodes=tuple(replace(node,completion='suspend',executor='event_loop') if node.id=='model' else node for node in block.nodes)) if block.id==p.plan.entry_block else block for block in p.plan.blocks))
result={'entry_mode':changed.entry_mode,'original_plan_node':p.plan.blocks[0].node('model').to_dict(),'changed_plan_node':changed.blocks[0].node('model').to_dict()}
try:
    view=bound_workflow_view(changed,p.javascript_bindings)
    n=next(n for n in view.nodes if n.id=='model')
    emitted=emit_workflow_module(changed,javascript_bindings=p.javascript_bindings)
    result.update(status='accepted',emitted_node=n.to_dict(),has_sync_entry='export function runWorkflow(' in emitted.source)
except Exception as exc:result.update(status='rejected',message=str(exc),code=getattr(exc,'code',''))
# Same canonical plan can receive either immediate or suspend metadata in the public binding builder.
async_plan=replace(p.plan,entry_mode='async')
metadata=[]
for completion in ('immediate','suspend'):
    b=build_javascript_binding_plan(async_plan,implementations={'example.model':{'completion':completion}},schemas=p.javascript_bindings.schemas.to_value())
    v=bound_workflow_view(async_plan,b)
    n=next(n for n in v.nodes if n.id=='model')
    metadata.append({'requested_completion':completion,'canonical_completion':async_plan.blocks[0].node('model').completion,'binding_completion':b.binding(('model',)).completion,'emitted_completion':n.completion,'emitted_executor':n.executor})
result['metadata_shadowing']=metadata
Path('/tmp/vibeflow-wide-js-binding-authority.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps(result,indent=2,ensure_ascii=False))
