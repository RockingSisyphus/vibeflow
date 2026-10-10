export function run(i: any, p: any) {
  return {result: i["math.loop_result"].value * 2 + i["math.offset_value"].value};
}
