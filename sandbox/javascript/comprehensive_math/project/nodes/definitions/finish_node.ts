import {defineNode} from "@vibeflow/plugin";
export const finish_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.finish",
  "display_name": "Finish",
  "description": "Finish in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.loop_result",
        "cardinality": "exactly_one",
        "display_name": "math.loop_result"
      },
      {
        "type": "math.offset_value",
        "cardinality": "exactly_one",
        "display_name": "math.offset_value"
      }
    ],
    "provides": [
      {
        "key": "result",
        "type": "math.result",
        "display_name": "result"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.loop_result": [
        "math.loop_result"
      ],
      "math.offset_value": [
        "math.offset_value"
      ]
    },
    "output_semantics": {
      "result": [
        "math.result"
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
        "ref": "nodes/finish.ts",
        "export": "run"
      }
    }
  ]
});
