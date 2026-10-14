export function run(inputs: any, params: any) {
  const copied=[...inputs["fixture.refs"].value];
  return {"fixture.forwarded": copied, "fixture.finished.forwarded":inputs["fixture.finished"].value};
}
