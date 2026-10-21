import {defineBaseLib} from "@vibeflow/plugin";
export const helpers = defineBaseLib({
  "id": "math.helpers",
  "display_name": "Multi-file arithmetic",
  "description": "Pure arithmetic with a declared support file.",
  "rulesets": [
    "vibeflow.base_lib"
  ],
  "dependencies": [],
  "external_packages": [],
  "implementations": [
    {
      "language": "typescript",
      "targets": [
        "node",
        "browser"
      ],
      "source": {
        "kind": "file",
        "ref": "base_lib/arithmetic.ts"
      },
      "implementation_files": [{"kind": "file", "ref": "scalar.ts"}]
    }
  ]
});
