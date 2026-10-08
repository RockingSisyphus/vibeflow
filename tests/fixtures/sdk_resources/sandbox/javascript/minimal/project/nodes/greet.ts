import { normalizeName } from "../base_lib/text.ts";

interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface GreetInputs {
  readonly "name.text": Envelope<string>;
}

interface GreetParams {
  readonly prefix: string;
}

interface GreetContext {
  readonly capabilities: {
    readonly "example.clock": {
      readonly now: (input: null) => Promise<number>;
    };
  };
}

export async function run(
  inputs: GreetInputs,
  params: GreetParams,
  context: GreetContext,
): Promise<{ readonly greeting: string }> {
  const name = normalizeName(inputs["name.text"].value);
  const timestamp = await context.capabilities["example.clock"].now(null);
  return { greeting: `${params.prefix}, ${name}! (${timestamp})` };
}
