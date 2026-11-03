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



export async function run(
  inputs: GreetInputs,
  params: GreetParams,
  context: any,
): Promise<{ readonly greeting: string }> {
  const name = normalizeName(inputs["name.text"].value);
  const timestamp = await (inputs as any)["app.session"].value.clock.now(null, {signal:context.signal});
  return { greeting: `${params.prefix}, ${name}! (${timestamp})` };
}

export const resource_6Definition=defineNode({"node_type":"vibeflow.node",...{"rulesets": ["vibeflow.python_io"], "id": "example.greet", "display_name": "Build greeting", "description": "Builds a greeting from a name and an application clock.", "version": "1.0.0", "flow_kind": "terminal", "contract": {"requires": [{"type": "name.text", "cardinality": "exactly_one", "display_name": "Name"}, {"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "provides": [{"key": "greeting", "type": "greeting.text", "display_name": "Greeting"}], "params_schema": {"prefix": {"type": "string"}}, "params_defaults": {"prefix": "Hello"}, "input_semantics": {"name.text": ["Name input consumed by this node."], "app.session": ["Application-owned event queue or API instance."]}, "output_semantics": {"greeting": ["Greeting output produced by this node."]}}, "base_libs": ["example.text"], "tags": ["example"], "targets": ["browser", "node"], "completion": "suspend"},run:run});
