export function check(context: { subject: {descriptor: {id: string}}, sources: {symbols(file: string): readonly unknown[]}, facts: {source_files: string[]} }) {
  const file = context.facts.source_files[0];
  const symbols = context.sources.symbols(file);
  return {records: {audit: {type_id: "sandbox.audit.v1", value: {node: context.subject.descriptor.id, symbols: symbols.length}}}, findings: []};
}
