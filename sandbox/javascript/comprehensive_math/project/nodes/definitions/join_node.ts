import {defineNode} from "@vibeflow/plugin";
export const join_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.join",
  "display_name": "Join",
  "description": "Join in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.term",
        "cardinality": "exactly_one",
        "display_name": "math.term"
      },
      {
        "type": "math.companion",
        "cardinality": "exactly_one",
        "display_name": "math.companion"
      }
    ],
    "provides": [
      {
        "key": "value",
        "type": "math.value",
        "display_name": "value"
      },
      {
        "key": "counter",
        "type": "math.counter",
        "display_name": "counter"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.term": [
        "math.term"
      ],
      "math.companion": [
        "math.companion"
      ]
    },
    "output_semantics": {
      "value": [
        "math.value"
      ],
      "counter": [
        "math.counter"
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
        "ref": "nodes/join.ts",
        "export": "run"
      }
    }
  ]
});
