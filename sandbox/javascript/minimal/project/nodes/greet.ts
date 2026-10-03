import {defineNode} from "@vibeflow/plugin";
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

export const resource_6Definition=defineNode({...{"rulesets": ["vibeflow.process"], "type_key": "example.greet", "display_name": "Build greeting", "description": "Builds a greeting from a name and an injected clock.", "version": "1.0.0", "flow_kind": "terminal", "contract": {"requires": [{"type": "name.text", "cardinality": "exactly_one", "display_name": "Name"}], "provides": [{"key": "greeting", "type": "greeting.text", "display_name": "Greeting"}], "params_schema": {"prefix": {"type": "string"}}, "params_defaults": {"prefix": "Hello"}, "input_semantics": {"name.text": ["Name input consumed by this node."]}, "output_semantics": {"greeting": ["Greeting output produced by this node."]}}, "base_libs": ["example.text"], "capabilities": [{"id": "example.clock", "operations": ["now"]}], "tags": ["example"], "targets": ["browser", "node"], "completion": "suspend"},run:run});
