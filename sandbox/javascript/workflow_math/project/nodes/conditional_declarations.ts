import {defineNode} from "@vibeflow/plugin";
export const receiveEvent = defineNode({"node_type":"vibeflow.node",
  id: "sandbox.receive_event",
  display_name: "Receive call event",
  description: "Forwards the call status and a numeric payload to conditional routes.",
  version: "1.0.0",
  flow_kind: "process",
  rulesets: ["vibeflow.process"],
  contract: {
    requires: [{ type: "sandbox.call.event", cardinality: "exactly_one", display_name: "Call event" }],
    provides: [
      { key: "route", type: "sandbox.call.route", display_name: "Route" },
      { key: "payload", type: "sandbox.number", display_name: "Payload" },
    ],
    input_semantics: { "sandbox.call.event": ["Call status: done, failed or unknown."] },
    output_semantics: { route: ["Status used by each edge condition."], payload: ["Numeric payload, always 42."] },
  },
  implementations: [{ language: "typescript", targets: ["node"],
    source: { kind: "file", ref: "nodes/conditional_routes.ts", export: "receiveEvent" } }],
});

export const finishCall = defineNode({"node_type":"vibeflow.node",
  id: "sandbox.finish_call",
  display_name: "Finish call",
  description: "Consumes exactly one payload and adds one when a route activates it.",
  version: "1.0.0",
  flow_kind: "process",
  rulesets: ["vibeflow.process"],
  contract: {
    requires: [{ type: "sandbox.number", cardinality: "exactly_one", display_name: "Payload" }],
    provides: [{ key: "result", type: "sandbox.math.result", display_name: "Result" }],
    input_semantics: { "sandbox.number": ["Payload delivered by an active route."] },
    output_semantics: { result: ["Payload plus one, expected to be 43."] },
  },
  implementations: [{ language: "typescript", targets: ["node"],
    source: { kind: "file", ref: "nodes/conditional_routes.ts", export: "finishCall" } }],
});
