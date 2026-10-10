export function run(i: any, p: any) {
  const counter = i["math.counter"].value + 1;
  return {next: i["math.value"].value + p.increment, counter, done: counter >= p.stop_after};
}
