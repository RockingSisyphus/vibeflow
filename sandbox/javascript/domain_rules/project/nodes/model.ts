type Envelope = Readonly<{value: number}>;
export function modelForward(value: number): number { return value * 2; }
export function run(inputs: Readonly<{"example.input": Envelope}>) {
  return {feature: modelForward(inputs["example.input"].value)};
}
