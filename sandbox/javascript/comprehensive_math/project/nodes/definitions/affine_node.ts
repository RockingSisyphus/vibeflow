import {defineNode} from "@vibeflow/plugin";
export const affine_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.affine",
  "display_name": "Affine",
  "description": "Affine in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.x",
        "cardinality": "exactly_one",
        "display_name": "math.x"
      }
    ],
    "provides": [
      {
        "key": "scaled",
        "type": "math.scaled",
        "display_name": "scaled"
      }
    ],
    "params_schema": {
      "gain": {
        "type": "number"
      },
      "shift": {
        "type": "number"
      }
    },
    "params_defaults": {
      "gain": 2,
      "shift": 1
    },
    "input_semantics": {
      "math.x": [
        "math.x"
      ]
    },
    "output_semantics": {
      "scaled": [
        "math.scaled"
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
        "ref": "nodes/affine.ts",
        "export": "run"
      }
    }
  ]
});
