import {defineRule, defineRuleset} from "@vibeflow/plugin";
export function check(context: any) {
  const findings = [];
  for (const node of context.facts.graph.nodes) {
    const descriptor = context.facts.node_catalog[node.type_used];
    if (!descriptor || descriptor.tags.includes("model_block")) continue;
    for (const implementation of descriptor.implementations) {
      const file = context.facts.source_files.find((file: string) => file === implementation.source.ref || file.endsWith("/" + implementation.source.ref));
      if (!file) continue;
      const occupants = new Set(context.facts.graph.nodes.flatMap((call: any) => {
        const resource = context.facts.node_catalog[call.type_used];
        return resource?.implementations.some((item: any) => item.source.ref === implementation.source.ref) ? [call.type_used] : [];
      }));
      if (occupants.size < 2) continue;
      for (const symbol of context.sources.symbols(file)) {
        if (symbol.kind !== "FunctionDeclaration" || symbol.name !== "modelForward") continue;
        findings.push({code:"EXAMPLE.MODEL.LOCATION", severity:"error", subject_id:node.type_used,
          source_location:{path:file,line:symbol.line,column:symbol.column},
          message:"Files containing modelForward must belong exclusively to model_block Nodes.",
          details:{node_type:node.type_used,call_paths:[[...context.subject.call_path,node.id]],ownership:context.sources.ownership(file)}});
      }
    }
  }
  return {findings};
}
export const modelFiles = defineRule({id:"example.model_files", check});
export const modelLayout = defineRuleset({id:"example.model_layout", workflow_default:true,
  calls:[{id:"files",rule_id:"example.model_files"}],entrypoints:{static:["files"]}});
