import { bridge } from "../helpers/node_builtin_bridge.ts";

export function run(): { readonly result: number } {
  void bridge;
  return { result: 1 };
}
