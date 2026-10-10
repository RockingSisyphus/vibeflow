export function run(i: any, p: any) {
  const selected = i["math.positive"] ?? i["math.negative"];
  return {term: selected.value};
}
