import { add } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface OptionalAddInputs {
  readonly "sandbox.x": Envelope<number>;
  readonly "sandbox.optional.offset": Envelope<number> | null;
}

export function run(
  inputs: OptionalAddInputs,
): { readonly result: number } {
  return {
    result: add(
      inputs["sandbox.x"].value,
      inputs["sandbox.optional.offset"]?.value ?? 0,
    ),
  };
}
