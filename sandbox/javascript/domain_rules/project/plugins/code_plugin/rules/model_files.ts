export function check(context: any) {
  const findings = [];
  for (const node of context.facts.graph.nodes) {
    const descriptor = context.facts.node_definitions[node.definition_id];
    if (!descriptor || descriptor.tags.includes("model_block")) continue;
    for (const implementation of descriptor.implementations) {
      const file = context.facts.source_files.find((file: string) => file === implementation.source.ref || file.endsWith("/" + implementation.source.ref));
      if (!file) continue;
      const occupants = new Set(context.facts.graph.nodes.flatMap((call: any) => {
        const resource = context.facts.node_definitions[call.definition_id];
        return resource?.implementations.some((item: any) => item.source.ref === implementation.source.ref) ? [call.definition_id] : [];
      }));
      if (occupants.size < 2) continue;
      for (const symbol of context.sources.symbols(file)) {
        if (symbol.kind !== "FunctionDeclaration" || symbol.name !== "modelForward") continue;
        findings.push({code:"EXAMPLE.MODEL.LOCATION", severity:"error", subject_id:node.definition_id,
          source_location:{path:file,line:symbol.line,column:symbol.column},
          message:"Files containing modelForward must belong exclusively to model_block Nodes.",
          details:{definition_id:node.definition_id,call_paths:[[...context.subject.call_path,node.id]],ownership:context.sources.ownership(file)}});
      }
    }
  }
  return {findings};
}
