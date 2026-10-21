import {defineNode} from "@vibeflow/plugin";
export const negative_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.negative",
  "display_name": "Negative",
  "description": "Negative in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.routed",
        "cardinality": "exactly_one",
        "display_name": "math.routed"
      }
    ],
    "provides": [
      {
        "key": "negative",
        "type": "math.negative",
        "display_name": "negative"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.routed": [
        "math.routed"
      ]
    },
    "output_semantics": {
      "negative": [
        "math.negative"
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
        "ref": "nodes/negative.ts",
        "export": "run"
      }
    }
  ]
});
