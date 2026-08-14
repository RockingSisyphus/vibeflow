interface Envelope<T> { readonly value: T; }

export function run(inputs: Readonly<Record<"payload.request", Envelope<unknown>>>): { readonly internal_payload: unknown } {
  return { internal_payload: inputs["payload.request"].value };
}
