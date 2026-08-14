interface Envelope<T> { readonly value: T; }

export function run(inputs: Readonly<Record<"payload.processed", Envelope<unknown>>>): { readonly response: unknown } {
  return { response: inputs["payload.processed"].value };
}
