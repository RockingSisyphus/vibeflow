import {defineNode} from "@vibeflow/plugin";
export const boundary_node = defineNode({"node_type":"vibeflow.node",
  "id": "math.boundary",
  "display_name": "Boundary",
  "description": "Boundary in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "terminal",
  "contract": {
    "requires": [],
    "provides": [],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {},
    "output_semantics": {}
  },
  "rulesets": [
    "vibeflow.io"
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
        "ref": "nodes/boundary.ts",
        "export": "run"
      }
    }
  ]
});
