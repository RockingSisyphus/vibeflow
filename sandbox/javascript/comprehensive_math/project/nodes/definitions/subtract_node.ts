import {defineNode} from "@vibeflow/plugin";
export const subtract_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.subtract",
  "display_name": "Subtract",
  "description": "Subtract in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.scaled",
        "cardinality": "exactly_one",
        "display_name": "math.scaled"
      }
    ],
    "provides": [
      {
        "key": "q",
        "type": "math.q",
        "display_name": "q"
      }
    ],
    "params_schema": {
      "amount": {
        "type": "number"
      }
    },
    "params_defaults": {
      "amount": 1
    },
    "input_semantics": {
      "math.scaled": [
        "math.scaled"
      ]
    },
    "output_semantics": {
      "q": [
        "math.q"
      ]
    }
  },
  "rulesets": [
    "math.process"
  ],
  "tags": [
    "comprehensive-math"
  ],
  "base_libs": [
    "math.helpers"
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
        "ref": "nodes/subtract.ts",
        "export": "run"
      }
    }
  ]
});
