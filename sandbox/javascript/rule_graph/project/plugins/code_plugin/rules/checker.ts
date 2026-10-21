import {appendFileSync} from "node:fs";

export function check(context, inputs, params) {
  const record = inputs.numbers;
  const proof = {handler:"checker",phase:context.phase,call:context.subject.rule_call_id ?? null,
    type_id:record.type_id,numbers:record.value,total:record.value.reduce((sum,value)=>sum+value,0)};
  if (params.marker) appendFileSync(params.marker,JSON.stringify(proof)+"\n");
  return {records:{proof:{type_id:"example.proof.v1",value:proof}}};
}
