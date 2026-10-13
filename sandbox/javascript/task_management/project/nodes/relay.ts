export function run(inputs: any, params: any) {
  const copied=[...inputs["fixture.refs"].value];
  return {"fixture.forwarded": [...copied.slice(0,1),...copied.filter(ref=>ref!==copied[0])]};
}
