import {defineNode} from "@vibeflow/plugin";
export const route_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.route",
  "display_name": "Route",
  "description": "Route in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "decision",
  "contract": {
    "requires": [
      {
        "type": "math.q",
        "cardinality": "exactly_one",
        "display_name": "math.q"
      }
    ],
    "provides": [
      {
        "key": "routed",
        "type": "math.routed",
        "display_name": "routed"
      },
      {
        "key": "nonnegative",
        "type": "math.nonnegative",
        "display_name": "nonnegative"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.q": [
        "math.q"
      ]
    },
    "output_semantics": {
      "routed": [
        "math.routed"
      ],
      "nonnegative": [
        "math.nonnegative"
      ]
    }
  },
  "rulesets": [
    "math.process"
  ],
  "tags": [
    "comprehensive-math"
  ],
  "implementations": [
    {
      "language": "typescript",
      "targets": [
        "node",
        "browser"
      ],
      "completion": "immediate",
      "source": {
        "kind": "file",
        "ref": "nodes/route.ts",
        "export": "run"
      }
    }
  ]
});
