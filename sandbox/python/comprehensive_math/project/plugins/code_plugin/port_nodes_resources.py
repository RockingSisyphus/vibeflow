from vibeflow.targets.python.sdk import capability,data_schema,ruleset,rule

portCapability = capability(**{'id': 'vibeflow.port', 'targets': ['python', 'browser', 'node'], 'display_name': 'VibeFlow Port', 'description': 'Host-provided receive/send queue boundary.', 'operations': {'receive': {'input_type': 'vibeflow.port.receive.request', 'output_type': 'vibeflow.port.receive.result', 'completion': 'suspend'}, 'send': {'input_type': 'vibeflow.port.send.request', 'output_type': 'vibeflow.port.send.result', 'completion': 'immediate'}}})

portSchema0 = data_schema(type_key='vibeflow.port.receive.request', schema={'type': 'object', 'required': ['port'], 'properties': {'port': {'type': 'string'}}, 'additionalProperties': False})

portSchema1 = data_schema(type_key='vibeflow.port.receive.result', schema={'type': 'object', 'required': ['value'], 'properties': {'value': {}}, 'additionalProperties': False})

portSchema2 = data_schema(type_key='vibeflow.port.send.request', schema={'type': 'object', 'required': ['port', 'value'], 'properties': {'port': {'type': 'string'}, 'value': {}}, 'additionalProperties': False})

portSchema3 = data_schema(type_key='vibeflow.port.send.result', schema={'type': 'null'})
