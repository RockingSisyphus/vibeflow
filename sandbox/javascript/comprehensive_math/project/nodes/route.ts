export function run(i: any, p: any) {
  const q = i["math.q"].value;
  return {routed: q, nonnegative: q >= 0};
}
