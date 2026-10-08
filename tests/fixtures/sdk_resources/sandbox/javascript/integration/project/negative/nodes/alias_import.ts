import { run as forbiddenRun } from "#forbidden-node";

export function run(): { readonly result: number } {
  void forbiddenRun;
  return { result: 1 };
}
