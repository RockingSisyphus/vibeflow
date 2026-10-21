from .port_nodes_resources import portCapability, portSchema0, portSchema1, portSchema2, portSchema3
from vibeflow.targets.python.sdk import Plugin, ruleset, base_lib, data_schema
from .rules.min_t import check as min_t
from .rules.advice import check as advice


source_rules = ruleset(**{'id': 'math.source_rules', 'calls': [{'id': 'letters', 'rule_id': 'math.min_t'}, {'id': 'advice', 'rule_id': 'math.t_advice'}], 'relations': [{'source': 'advice', 'target': 'letters', 'kind': 'requires', 'bindings': {'count': 'count'}}], 'entrypoints': {'static': ['letters', 'advice'], 'run': ['letters', 'advice']}})

process_rules = ruleset(**{'id': 'math.process', 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'}], 'relations': [{'source': '$self', 'target': 'native/maintainability', 'kind': 'overrides', 'params': {'policy': {'node_source': {'warn_lines': 4, 'max_lines': 500}}}}], 'entrypoints': {'import': ['native'], 'static': ['native'], 'run': ['native']}})

schema_0 = data_schema(**{'type_key': 'math.companion', 'representation': 'json', 'schema': {'type': 'number'}})

schema_1 = data_schema(**{'type_key': 'math.counter', 'representation': 'json', 'schema': {'type': 'number'}})

schema_2 = data_schema(**{'type_key': 'math.done', 'representation': 'json', 'schema': {'type': 'boolean'}})

schema_3 = data_schema(**{'type_key': 'math.history', 'representation': 'json', 'schema': {'type': 'array', 'items': {'type': 'number'}}})

schema_4 = data_schema(**{'type_key': 'math.iterations', 'representation': 'json', 'schema': {'type': 'number'}})

schema_5 = data_schema(**{'type_key': 'math.loop_result', 'representation': 'json', 'schema': {'type': 'number'}})

schema_6 = data_schema(**{'type_key': 'math.negative', 'representation': 'json', 'schema': {'type': 'number'}})

schema_7 = data_schema(**{'type_key': 'math.next', 'representation': 'json', 'schema': {'type': 'number'}})

schema_8 = data_schema(**{'type_key': 'math.next_counter', 'representation': 'json', 'schema': {'type': 'number'}})

schema_9 = data_schema(**{'type_key': 'math.nonnegative', 'representation': 'json', 'schema': {'type': 'boolean'}})

schema_10 = data_schema(**{'type_key': 'math.offset', 'representation': 'json', 'schema': {'type': 'number'}})

schema_11 = data_schema(**{'type_key': 'math.offset_value', 'representation': 'json', 'schema': {'type': 'number'}})

schema_12 = data_schema(**{'type_key': 'math.positive', 'representation': 'json', 'schema': {'type': 'number'}})

schema_13 = data_schema(**{'type_key': 'math.q', 'representation': 'json', 'schema': {'type': 'number'}})

schema_14 = data_schema(**{'type_key': 'math.result', 'representation': 'json', 'schema': {'type': 'number'}})

schema_15 = data_schema(**{'type_key': 'math.routed', 'representation': 'json', 'schema': {'type': 'number'}})

schema_16 = data_schema(**{'type_key': 'math.scaled', 'representation': 'json', 'schema': {'type': 'number'}})

schema_17 = data_schema(**{'type_key': 'math.term', 'representation': 'json', 'schema': {'type': 'number'}})

schema_18 = data_schema(**{'type_key': 'math.value', 'representation': 'json', 'schema': {'type': 'number'}})

schema_19 = data_schema(**{'type_key': 'math.x', 'representation': 'json', 'schema': {'type': 'number'}})

plugin = Plugin(id='math.python', resources=[portCapability, portSchema0, portSchema1, portSchema2, portSchema3, min_t, advice, source_rules, process_rules, schema_0, schema_1, schema_2, schema_3, schema_4, schema_5, schema_6, schema_7, schema_8, schema_9, schema_10, schema_11, schema_12, schema_13, schema_14, schema_15, schema_16, schema_17, schema_18, schema_19])
