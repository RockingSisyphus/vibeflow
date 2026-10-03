import {definePlugin,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension} from "@vibeflow/plugin";
import {resource_0Definition as resource_0} from "./nodes/calculation.ts";

import {resource_1Definition as resource_1} from "./nodes/calculation.ts";

import {resource_2Definition as resource_2} from "./rules/checker.ts";

import {resource_3Definition as resource_3} from "./rules/provider.ts";

import {resource_4Definition as resource_4} from "./rules/provider.ts";

import {resource_5Definition as resource_5} from "./rules/provider.ts";

export const resource_6=defineRuleset({"id": "example.rule_graph", "calls": [{"id": "provider", "rule_id": "example.number_provider"}, {"id": "checker", "rule_id": "example.number_checker"}], "relations": [{"source": "checker", "target": "provider", "kind": "requires", "bindings": {"numbers": "numbers"}}]});

export const resource_7=defineRuleset({"id": "example.nested", "calls": [{"id": "pair", "ruleset_id": "example.shared_pair"}]});

export const resource_8=defineRuleset({"id": "example.shared_pair", "calls": [{"id": "provider", "rule_id": "example.number_provider"}, {"id": "checker", "rule_id": "example.number_checker"}], "relations": [{"source": "checker", "target": "provider", "kind": "requires", "bindings": {"numbers": "numbers"}}]});

export const resource_9=defineDataSchema({"type_key": "example.input", "representation": "json", "schema": {"type": "number"}});

export const resource_10=defineDataSchema({"type_key": "example.output", "representation": "json", "schema": {"type": "number"}});

export const plugin=definePlugin({id:"example.javascript.rule_graph",resources:[resource_0,resource_1,resource_2,resource_3,resource_4,resource_5,resource_6,resource_7,resource_8,resource_9,resource_10]});
