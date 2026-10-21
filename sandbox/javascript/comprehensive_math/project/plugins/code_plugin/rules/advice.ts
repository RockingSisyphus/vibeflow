import {defineRule} from "@vibeflow/plugin";

export function check(context: any, inputs: any) {
  const record = inputs.count;
  const evidence = record.value;
  if (evidence.actual >= evidence.minimum) return {findings: []};
  return {findings: [{code: "MATH.T_ADVICE", severity: "warning", subject_type: "node",
    subject_id: context.subject.descriptor.id,
    source_location: {path: evidence.path, line: evidence.line, column: evidence.column},
    message: "The source measurement reached this dependent rule; review the Node convention.",
    details: {actual: evidence.actual, minimum: evidence.minimum, record_type: record.type_id,
      suggestion: "Review the declared implementation."},
  }]};
}

export const advice = defineRule({id: "math.t_advice", scope: "source",
  inputs: {count: "math.t_count.v1"}, check});
