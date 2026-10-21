import {defineNode} from "@vibeflow/plugin";
export const choice_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.choice",
  "display_name": "Choice",
  "description": "Choice in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.positive",
        "cardinality": "optional_one",
        "display_name": "math.positive"
      },
      {
        "type": "math.negative",
        "cardinality": "optional_one",
        "display_name": "math.negative"
      }
    ],
    "provides": [
      {
        "key": "term",
        "type": "math.term",
        "display_name": "term"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.positive": [
        "math.positive"
      ],
      "math.negative": [
        "math.negative"
      ]
    },
    "output_semantics": {
      "term": [
        "math.term"
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
        "ref": "nodes/choice.ts",
        "export": "run"
      }
    }
  ]
});
