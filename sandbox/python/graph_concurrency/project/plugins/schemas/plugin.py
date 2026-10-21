from vibeflow.targets.python.sdk import Plugin,data_schema
r14=data_schema(**{'type_key': 'scenario', 'representation': 'json', 'schema': {'type': 'string'}})
r15=data_schema(**{'type_key': 'receipt', 'representation': 'json', 'schema': {'type': 'integer'}})
r16=data_schema(**{'type_key': 'report', 'representation': 'json', 'schema': {'type': 'array', 'items': {'type': 'integer'}}})
plugin=Plugin(id="graph.concurrency",resources=[r14,r15,r16])
