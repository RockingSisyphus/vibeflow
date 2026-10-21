type Envelope = Readonly<{value: number}>;
export function run(inputs: Readonly<{"example.feature": Envelope}>) {
  return {output: inputs["example.feature"].value + 1};
}
