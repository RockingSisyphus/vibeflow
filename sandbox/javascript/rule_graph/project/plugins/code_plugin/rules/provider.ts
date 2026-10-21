import {appendFileSync} from "node:fs";

export function check(context, inputs, params) {
  const mode = params.mode;
  const numbers = mode === "empty" ? [] : [params.value];
  if (params.marker) appendFileSync(params.marker, JSON.stringify({handler:"provider", phase:context.phase, call:context.subject.rule_call_id ?? null, numbers})+"\n");
  const findings = ["warning", "error"].includes(mode) ? [{code:"EXAMPLE.PROVIDER.FINDING", severity:mode,
    message:"A provider can report a finding while supplying valid facts.", source_location:{path:params.source,line:4,column:1}}] : [];
  if (["failed", "unavailable"].includes(mode)) return {state:mode, findings};
  if (mode === "missing") return {records:{}, findings};
  return {records:{numbers:{type_id:mode === "wrong_type" ? "example.wrong.v1" : "example.numbers.v1",value:numbers}},findings};
}

export function replacement(context, inputs, params) {
  return check(context, inputs, {...params, value:params.value+10});
}
