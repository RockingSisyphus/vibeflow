import {definePlugin,defineRuleset,defineDataSchema,defineBaseLib,defineCapability,defineHostExtension} from "@vibeflow/plugin";
import {resource_0Definition as resource_0} from "./nodes/boundary.ts";

import {resource_1Definition as resource_1} from "./nodes/model.ts";

import {resource_2Definition as resource_2} from "./nodes/transform.ts";

import {resource_3Definition as resource_3} from "./rules/model_definition.ts";

export const resource_4=defineRuleset({"id": "example.model_domain", "calls": [{"id": "model_definition", "rule_id": "example.model_definition"}], "entrypoints": {"static": ["model_definition"], "run": ["model_definition"]}});

export const resource_5=defineDataSchema({"type_key": "example.feature", "representation": "json", "schema": {"type": "number"}});

export const resource_6=defineDataSchema({"type_key": "example.input", "representation": "json", "schema": {"type": "number"}});

export const resource_7=defineDataSchema({"type_key": "example.output", "representation": "json", "schema": {"type": "number"}});

import {modelFiles,modelLayout} from "./rules/model_files.ts";

export const plugin=definePlugin({id:"example.javascript.domain_rules",resources:[resource_0,resource_1,resource_2,resource_3,resource_4,resource_5,resource_6,resource_7,modelFiles,modelLayout]});
