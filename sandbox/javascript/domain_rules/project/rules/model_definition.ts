import {defineRule} from "@vibeflow/plugin";
type SymbolInfo = Readonly<{kind: string; name: string; path: string; line: number; column: number}>;
type Context = Readonly<{
  subject: {descriptor: {type_key: string; tags: readonly string[]}};
  facts: {source_files: readonly string[]};
  sources: {reachable(path: string): readonly string[]; symbols(path: string): readonly SymbolInfo[]; ownership(path: string): unknown};
}>;
export function check(context: Context, inputs: unknown, params: {model_tag: string}) {
  const descriptor = context.subject.descriptor;
  const files = [...new Set(context.facts.source_files.flatMap(file => context.sources.reachable(file)))];
  const definitions = files.flatMap(file => context.sources.symbols(file)).filter(symbol => symbol.kind === "FunctionDeclaration" && symbol.name === "modelForward");
  const findings = definitions.filter(() => !descriptor.tags.includes(params.model_tag)).map(symbol => ({
    code: "EXAMPLE.MODEL.LOCATION", severity: "error", subject_id: descriptor.type_key,
    source_location: {path: symbol.path, line: symbol.line, column: symbol.column},
    message: "modelForward definitions must belong to a model_block Node.",
    details: {ownership: context.sources.ownership(symbol.path)},
  }));
  if (descriptor.tags.includes(params.model_tag) && definitions.length !== 1) findings.push({
    code: "EXAMPLE.MODEL.ONE_BLOCK", severity: "error", subject_id: descriptor.type_key,
    source_location: {path: context.facts.source_files[0] ?? "", line: 1, column: 1},
    message: "A model_block must define exactly one modelForward function.", details: {ownership: descriptor.type_key},
  });
  return {findings};
}

export const resource_3Definition=defineRule({...{"id": "example.model_definition", "description": "modelForward belongs to model_block and each block defines one modelForward.", "params_schema": {"model_tag": {"type": "string"}}, "params_defaults": {"model_tag": "model_block"}},check:check});
