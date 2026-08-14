interface Envelope<T> { readonly value: T; }

export function run(inputs: Readonly<Record<"payload.internal", Envelope<unknown>>>): { readonly processed_payload: unknown } {
  // BUSINESS CODE: replace this pass-through with the real transformation.
  return { processed_payload: inputs["payload.internal"].value };
}
