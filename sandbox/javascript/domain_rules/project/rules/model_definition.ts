type SymbolInfo = Readonly<{kind: string; name: string; path: string; line: number; column: number}>;
type Context = Readonly<{
  subject: {descriptor: {type_key: string; category: string}};
  facts: {source_files: readonly string[]};
  sources: {reachable(path: string): readonly string[]; symbols(path: string): readonly SymbolInfo[]; ownership(path: string): unknown};
}>;
export function check(context: Context) {
  const descriptor = context.subject.descriptor;
  const files = [...new Set(context.facts.source_files.flatMap(file => context.sources.reachable(file)))];
  const definitions = files.flatMap(file => context.sources.symbols(file)).filter(symbol => symbol.kind === "FunctionDeclaration" && symbol.name === "modelForward");
  const findings = definitions.filter(() => descriptor.category !== "model_block").map(symbol => ({
    code: "EXAMPLE.MODEL.LOCATION", severity: "error", subject_id: descriptor.type_key,
    source_location: {path: symbol.path, line: symbol.line, column: symbol.column},
    message: "modelForward definitions must belong to a model_block Node.",
    details: {ownership: context.sources.ownership(symbol.path)},
  }));
  if (descriptor.category === "model_block" && definitions.length !== 1) findings.push({
    code: "EXAMPLE.MODEL.ONE_BLOCK", severity: "error", subject_id: descriptor.type_key,
    source_location: {path: context.facts.source_files[0] ?? "", line: 1, column: 1},
    message: "A model_block must define exactly one modelForward function.", details: {ownership: descriptor.type_key},
  });
  return {findings};
}
