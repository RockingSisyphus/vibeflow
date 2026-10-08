import { add } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface FanoutInputs {
  readonly "sandbox.x": Envelope<number>;
}

export function run(
  inputs: FanoutInputs,
): { readonly added_branch: number } {
  return {
    added_branch: add(inputs["sandbox.x"].value, 1),
  };
}
