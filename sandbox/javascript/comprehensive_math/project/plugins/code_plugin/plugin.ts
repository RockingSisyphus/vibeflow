import {portCapability,portSchema0,portSchema1,portSchema2,portSchema3} from "./port_resources";
import {definePlugin, defineNode, defineRule, defineRuleset, defineBaseLib, defineDataSchema} from "@vibeflow/plugin";
import {min_t} from "./rules/min_t.ts";
import {advice} from "./rules/advice.ts";



























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

export const plugin = definePlugin({id:"math.javascript", resources:[ portCapability, portSchema0, portSchema1, portSchema2, portSchema3, min_t, advice, source_rules, process_rules, schema_0, schema_1, schema_2, schema_3, schema_4, schema_5, schema_6, schema_7, schema_8, schema_9, schema_10, schema_11, schema_12, schema_13, schema_14, schema_15, schema_16, schema_17, schema_18, schema_19]});
