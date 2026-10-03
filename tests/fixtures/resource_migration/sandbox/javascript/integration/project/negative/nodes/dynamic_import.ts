interface Envelope<T> {
  readonly value: T;
}

interface InvalidInputs {
  readonly "sandbox.number": Envelope<number>;
}

export async function run(
  inputs: InvalidInputs,
): Promise<{ readonly result: number }> {
  const modulePath = "../../base_lib/math.ts";
  const math = await import(modulePath);
  return {
    result: math.add(inputs["sandbox.number"].value, 0),
  };
}
