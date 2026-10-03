import { isNonNegative } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface RouteInputs {
  readonly "sandbox.x": Envelope<number>;
}

export function run(inputs: RouteInputs): {
  readonly forwarded: number;
  readonly positive: boolean;
} {
  const value = inputs["sandbox.x"].value;
  return {
    forwarded: value,
    positive: isNonNegative(value),
  };
}
