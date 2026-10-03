import { run as forbiddenRun } from "../barrels/math.ts";

export function run(): { readonly result: number } {
  void forbiddenRun;
  return { result: 1 };
}
