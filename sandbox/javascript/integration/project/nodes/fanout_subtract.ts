import { subtract } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface FanoutInputs {
  readonly "sandbox.x": Envelope<number>;
}

export function run(
  inputs: FanoutInputs,
): { readonly subtracted_branch: number } {
  return {
    subtracted_branch: subtract(inputs["sandbox.x"].value, 1),
  };
}
