import {defineRule} from "@vibeflow/plugin";

export function check(context: any, inputs: unknown, params: {minimum: number}) {
  const implementation = context.facts.sources.find((source: any) => source.owner === context.subject.descriptor.type_key);
  if (!implementation) throw new Error("Node implementation source is unavailable");
  const symbol = context.sources.symbols(implementation.path).find((item: any) => item.kind === "FunctionDeclaration" && item.name === (implementation.export ?? "run"));
  if (!symbol) throw new Error("Node implementation symbol is unavailable");
  const evidence = {actual: (symbol.text.match(/t/g) ?? []).length,
    minimum: params.minimum, path: symbol.path, line: symbol.line, column: symbol.column};
  const findings = evidence.actual < evidence.minimum ? [{
    code: "MATH.MIN_T", severity: "warning", subject_type: "node",
    subject_id: context.subject.descriptor.type_key,
    source_location: {path: evidence.path, line: evidence.line, column: evidence.column},
    message: `Node source has ${evidence.actual} lowercase t characters; expected at least ${evidence.minimum}.`,
    details: {...evidence, counting_scope: "declared implementation"},
  }] : [];
  return {records: {count: {type_id: "math.t_count.v1", value: evidence}}, findings};
}

export const min_t = defineRule({id: "math.min_t", scope: "source",
  description: "Count lowercase t in the declared Node function source.",
  outputs: {count: "math.t_count.v1"},
  params_schema: {minimum: {type: "integer", minimum: 0}},
  params_defaults: {minimum: 10}, check});
