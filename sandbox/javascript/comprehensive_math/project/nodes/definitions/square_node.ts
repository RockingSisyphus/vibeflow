import {defineNode} from "@vibeflow/plugin";
export const square_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.square",
  "display_name": "Square",
  "description": "Square in the composite formula.",
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
        "key": "positive",
        "type": "math.positive",
        "display_name": "positive"
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
      "positive": [
        "math.positive"
      ]
    }
  },
  "rulesets": [
    "math.process",
    "math.source_rules"
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
        "ref": "nodes/square.ts",
        "export": "run"
      }
    }
  ]
});
