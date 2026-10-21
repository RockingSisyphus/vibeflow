from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,data_schema,base_lib,capability,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource
















































































































































resource_144 = rule(**{'id': 'sandbox.bad-shape', 'level': 'graph',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/checks.py',
                                 'export': 'bad_shape'}}],
 'source': {'kind': 'file', 'ref': 'rules/checks.py', 'export': 'bad_shape'}})

resource_145 = rule(**{'id': 'sandbox.fail', 'level': 'graph',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/checks.py',
                                 'export': 'fail'}}],
 'source': {'kind': 'file', 'ref': 'rules/checks.py', 'export': 'fail'}})

resource_146 = rule(**{'id': 'sandbox.findings', 'level': 'graph',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/checks.py',
                                 'export': 'finding'}}],
 'source': {'kind': 'file', 'ref': 'rules/checks.py', 'export': 'finding'}})

resource_147 = rule(**{'id': 'sandbox.missing-record', 'level': 'graph',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/checks.py',
                                 'export': 'missing_record'}}],
 'outputs': {'required': 'sandbox.required.v1'},
 'source': {'kind': 'file',
            'ref': 'rules/checks.py',
            'export': 'missing_record'}})

resource_148 = ruleset(**{'id': 'sandbox.bad-shape',
 'calls': [{'id': 'check', 'rule_id': 'sandbox.bad-shape'}],
 'entrypoints': {'static': ['check'], 'run': ['check']}})

resource_149 = ruleset(**{'id': 'sandbox.fail',
 'calls': [{'id': 'check', 'rule_id': 'sandbox.fail'}],
 'entrypoints': {'static': ['check'], 'run': ['check']}})

resource_150 = ruleset(**{'id': 'sandbox.findings',
 'calls': [{'id': 'check', 'rule_id': 'sandbox.findings'}],
 'entrypoints': {'static': ['check'], 'run': ['check']}})

resource_151 = ruleset(**{'id': 'sandbox.missing-record',
 'calls': [{'id': 'check', 'rule_id': 'sandbox.missing-record'}],
 'entrypoints': {'static': ['check'], 'run': ['check']}})





plugin = Plugin(id='fixture.resources', resources=[resource_144, resource_145, resource_146, resource_147, resource_148, resource_149, resource_150, resource_151])
