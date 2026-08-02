import { readFileSync } from "node:fs";

interface Envelope<T> {
  readonly value: T;
}

interface InvalidInputs {
  readonly "sandbox.number": Envelope<number>;
}

export function run(
  inputs: InvalidInputs,
): { readonly result: number } {
  if (typeof readFileSync !== "function") {
    throw new Error("unreachable");
  }
  return {
    result: inputs["sandbox.number"].value,
  };
}
