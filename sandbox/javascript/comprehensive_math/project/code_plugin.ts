import {definePlugin, defineNode, defineRule, defineRuleset, defineBaseLib, defineDataSchema} from "@vibeflow/plugin";
import {min_t} from "./rules/min_t.ts";
import {advice} from "./rules/advice.ts";

const boundary_node = defineNode({
  "type_key": "math.boundary",
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

const affine_node = defineNode({
  "type_key": "math.affine",
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

const subtract_node = defineNode({
  "type_key": "math.subtract",
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

const route_node = defineNode({
  "type_key": "math.route",
  "display_name": "Route",
  "description": "Route in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "decision",
  "contract": {
    "requires": [
      {
        "type": "math.q",
        "cardinality": "exactly_one",
        "display_name": "math.q"
      }
    ],
    "provides": [
      {
        "key": "routed",
        "type": "math.routed",
        "display_name": "routed"
      },
      {
        "key": "nonnegative",
        "type": "math.nonnegative",
        "display_name": "nonnegative"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.q": [
        "math.q"
      ]
    },
    "output_semantics": {
      "routed": [
        "math.routed"
      ],
      "nonnegative": [
        "math.nonnegative"
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
        "ref": "nodes/route.ts",
        "export": "run"
      }
    }
  ]
});

const square_node = defineNode({
  "type_key": "math.square",
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

const negative_node = defineNode({
  "type_key": "math.negative",
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

const choice_node = defineNode({
  "type_key": "math.choice",
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

const companion_node = defineNode({
  "type_key": "math.companion",
  "display_name": "Companion",
  "description": "Companion in the composite formula.",
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
        "key": "companion",
        "type": "math.companion",
        "display_name": "companion"
      }
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {
      "math.x": [
        "math.x"
      ]
    },
    "output_semantics": {
      "companion": [
        "math.companion"
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
        "ref": "nodes/companion.ts",
        "export": "run"
      }
    }
  ]
});

const join_node = defineNode({
  "type_key": "math.join",
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

const step_node = defineNode({
  "type_key": "math.step",
  "display_name": "Step",
  "description": "Step in the composite formula.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {
        "type": "math.value",
        "cardinality": "exactly_one",
        "display_name": "math.value"
      },
      {
        "type": "math.counter",
        "cardinality": "exactly_one",
        "display_name": "math.counter"
      }
    ],
    "provides": [
      {
        "key": "next",
        "type": "math.next",
        "display_name": "next"
      },
      {
        "key": "counter",
        "type": "math.next_counter",
        "display_name": "counter"
      },
      {
        "key": "done",
        "type": "math.done",
        "display_name": "done"
      }
    ],
    "params_schema": {
      "increment": {
        "type": "number"
      },
      "stop_after": {
        "type": "integer"
      }
    },
    "params_defaults": {
      "increment": 2,
      "stop_after": 3
    },
    "input_semantics": {
      "math.value": [
        "math.value"
      ],
      "math.counter": [
        "math.counter"
      ]
    },
    "output_semantics": {
      "next": [
        "math.next"
      ],
      "counter": [
        "math.next_counter"
      ],
      "done": [
        "math.done"
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
        "ref": "nodes/step.ts",
        "export": "run"
      }
    }
  ]
});

const offset_node = defineNode({
  "type_key": "math.offset",
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

const finish_node = defineNode({
  "type_key": "math.finish",
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

const helpers = defineBaseLib({
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
      "implementation_files": [
        {
          "kind": "file",
          "ref": "base_lib/scalar.ts"
        }
      ]
    }
  ]
});

const source_rules = defineRuleset({
  "id": "math.source_rules",
  "calls": [
    {
      "id": "letters",
      "rule_id": "math.min_t"
    },
    {
      "id": "advice",
      "rule_id": "math.t_advice"
    }
  ],
  "relations": [
    {
      "source": "advice",
      "target": "letters",
      "kind": "requires",
      "bindings": {
        "count": "count"
      }
    }
  ],
  "entrypoints": {
    "static": [
      "letters",
      "advice"
    ],
    "run": [
      "letters",
      "advice"
    ]
  }
});

const process_rules = defineRuleset({
  "id": "math.process",
  "calls": [
    {
      "id": "native",
      "ruleset_id": "vibeflow.process"
    }
  ],
  "relations": [
    {
      "source": "$self",
      "target": "native/maintainability",
      "kind": "overrides",
      "params": {
        "policy": {
          "node_source": {
            "warn_lines": 4,
            "max_lines": 500
          }
        }
      }
    }
  ],
  "entrypoints": {
    "import": [
      "native"
    ],
    "static": [
      "native"
    ],
    "run": [
      "native"
    ]
  }
});

const schema_0 = defineDataSchema({"type_key": "math.companion", "representation": "json", "schema": {"type": "number"}});

const schema_1 = defineDataSchema({"type_key": "math.counter", "representation": "json", "schema": {"type": "number"}});

const schema_2 = defineDataSchema({"type_key": "math.done", "representation": "json", "schema": {"type": "boolean"}});

const schema_3 = defineDataSchema({"type_key": "math.history", "representation": "json", "schema": {"type": "array", "items": {"type": "number"}}});

const schema_4 = defineDataSchema({"type_key": "math.iterations", "representation": "json", "schema": {"type": "number"}});

const schema_5 = defineDataSchema({"type_key": "math.loop_result", "representation": "json", "schema": {"type": "number"}});

const schema_6 = defineDataSchema({"type_key": "math.negative", "representation": "json", "schema": {"type": "number"}});

const schema_7 = defineDataSchema({"type_key": "math.next", "representation": "json", "schema": {"type": "number"}});

const schema_8 = defineDataSchema({"type_key": "math.next_counter", "representation": "json", "schema": {"type": "number"}});

const schema_9 = defineDataSchema({"type_key": "math.nonnegative", "representation": "json", "schema": {"type": "boolean"}});

const schema_10 = defineDataSchema({"type_key": "math.offset", "representation": "json", "schema": {"type": "number"}});

const schema_11 = defineDataSchema({"type_key": "math.offset_value", "representation": "json", "schema": {"type": "number"}});

const schema_12 = defineDataSchema({"type_key": "math.positive", "representation": "json", "schema": {"type": "number"}});

const schema_13 = defineDataSchema({"type_key": "math.q", "representation": "json", "schema": {"type": "number"}});

const schema_14 = defineDataSchema({"type_key": "math.result", "representation": "json", "schema": {"type": "number"}});

const schema_15 = defineDataSchema({"type_key": "math.routed", "representation": "json", "schema": {"type": "number"}});

const schema_16 = defineDataSchema({"type_key": "math.scaled", "representation": "json", "schema": {"type": "number"}});

const schema_17 = defineDataSchema({"type_key": "math.term", "representation": "json", "schema": {"type": "number"}});

const schema_18 = defineDataSchema({"type_key": "math.value", "representation": "json", "schema": {"type": "number"}});

const schema_19 = defineDataSchema({"type_key": "math.x", "representation": "json", "schema": {"type": "number"}});

export const plugin = definePlugin({id:"math.javascript", resources:[boundary_node, affine_node, subtract_node, route_node, square_node, negative_node, choice_node, companion_node, join_node, step_node, offset_node, finish_node, helpers, min_t, advice, source_rules, process_rules, schema_0, schema_1, schema_2, schema_3, schema_4, schema_5, schema_6, schema_7, schema_8, schema_9, schema_10, schema_11, schema_12, schema_13, schema_14, schema_15, schema_16, schema_17, schema_18, schema_19]});
