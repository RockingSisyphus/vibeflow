import {defineNode} from "@vibeflow/plugin";
export const offset_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.offset",
  "display_name": "Offset",
  "description": "Offset in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.offset",
        "cardinality": "optional_one",
        "display_name": "math.offset"
      }
    ],
    "provides": [
      {
        "key": "offset",
        "type": "math.offset_value",
        "display_name": "offset"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.offset": [
        "math.offset"
      ]
    },
    "output_semantics": {
      "offset": [
        "math.offset_value"
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
        "ref": "nodes/offset.ts",
        "export": "run"
      }
    }
  ]
});
