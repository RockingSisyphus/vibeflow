"""Bounded in-process probes; their results contain summaries, never large DAGs."""

RECORD_PROBE = r'''
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from vibeflow.core.rules import RuleContext, RuleRecord

def count(value):
    seen, pending = set(), [value]
    while pending:
        current = pending.pop()
        if isinstance(current, (Mapping, tuple, list, set, frozenset)) or is_dataclass(current):
            if id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, Mapping):
                pending.extend(current.values())
            elif is_dataclass(current):
                pending.extend(getattr(current, field.name) for field in fields(current))
            else:
                pending.extend(current)
    return len(seen)

rows = {}
for kind in ('tuple', 'mapping'):
    value = 1
    for _ in range(12):
        value = (value, value) if kind == 'tuple' else {'left':value, 'right':value}
    frozen = RuleRecord('case.graph', value).value
    control = RuleContext(facts={'graph':value}).facts['graph']
    shared = frozen[0] is frozen[1] if kind == 'tuple' else frozen['left'] is frozen['right']
    rows[kind] = {'input_objects':count(value), 'record_objects':count(frozen),
                  'context_objects':count(control), 'shared':shared}
shared = {'items':[{'value':1}]}
record = RuleRecord('case.graph', (shared, shared))
try:
    record.value[0]['items'][0]['value'] = 2
except TypeError:
    blocked = True
else:
    blocked = False
shared['items'][0]['value'] = 9
rows['mixed'] = {'record_objects':count(record.value), 'shared':record.value[0] is record.value[1],
                 'readonly':blocked, 'isolated':record.value[0]['items'][0]['value'] == 1}
@dataclass(frozen=True)
class Evidence:
    details: object
shared = Evidence({'items':[1]})
record = RuleRecord('case.graph', (shared, shared))
rows['native'] = {'type_preserved':type(record.value[0]) is Evidence,
                  'shared':record.value[0] is record.value[1]}
cycles = {}
value = []; value.append(value); cycles['list'] = value
value = {}; value['self'] = value; cycles['mapping'] = value
value = []; parent = (value,); value.append(parent); cycles['tuple_list'] = parent
value = {}; parent = Evidence(value); value['self'] = parent; cycles['dataclass'] = parent
for name, value in cycles.items():
    try:
        RuleRecord('case.graph', value)
    except ValueError as error:
        rows['cycle_' + name] = {'rejected':True, 'cycle_message':'cyclic' in str(error)}
    else:
        rows['cycle_' + name] = {'rejected':False, 'cycle_message':False}
small = RuleRecord('case.graph', ((1, 2), (1, 2))).to_dict()
rows['json_boundary'] = {'value':small['value'], 'ordinary_json':json.loads(json.dumps(small)) == small}
print(json.dumps(rows))
'''

CACHE_PROBE = r'''
import json, sys
from dataclasses import dataclass
from unittest.mock import patch
from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan

mode = sys.argv[1]
resources = {'provider':RuleDescriptor('provider', outputs={'data':'case.data'}),
             'consumer':RuleDescriptor('consumer', inputs={'data':'case.data'}, scope='source')}
selection = RulesetDescriptor('case.cache', (RuleCall('p1','provider'), RuleCall('p2','provider'), RuleCall('c1','consumer'), RuleCall('c2','consumer')),
    (RuleRelation('c1','p1','requires',bindings={'data':'data'}), RuleRelation('c2','p2','requires',bindings={'data':'data'})))
plan = compile_ruleset(selection, rules=resources)
value = 1
for _ in range(8):
    value = (value, value)
def tree(depth):
    return 1 if not depth else (tree(depth-1), tree(depth-1))
@dataclass(frozen=True)
class First:
    value: object
@dataclass(frozen=True)
class Second:
    value: object
values = {
    'same_dag': (value, value), 'equal_tree':(value,tree(8)),
    'different_leaf':((1,1),(1,2)), 'mapping_order':({'b':2,'a':1},{'a':1,'b':2}),
    'integer_float':(1,1.0), 'integer_boolean':(1,True), 'signed_zero':(-0.0,0.0),
    'native_types':(First(1),Second(1)), 'native_vs_json':(First(1),{'value':1}),
    'set_vs_sequence':(frozenset({1,2}),(1,2)),
}[mode]
counters = {'provider':0, 'consumer':0, 'internal_record_projection':0}
original = RuleRecord.to_dict

def projected(self):
    caller = sys._getframe(1)
    while caller is not None and caller.f_code.co_name != '_key':
        caller = caller.f_back
    if caller is not None:
        counters['internal_record_projection'] += 1
    return original(self)

def provider(context, inputs, params):
    counters['provider'] += 1
    return RuleResult({'data':RuleRecord('case.data',values[0 if context.subject['rule_call_id']=='p1' else 1])})
def consumer(context, inputs, params):
    counters['consumer'] += 1
    return RuleResult()
with patch.object(RuleRecord,'to_dict',projected):
    result = execute_rule_plan(plan, RuleContext(subject={'source_identity':'standalone.py:Node'}), handlers={'provider':provider,'consumer':consumer})
print(json.dumps({'status':result.status, **counters}))
'''

CACHE_IDENTITY_PROBE = r'''
import json, sys
from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan

mode = sys.argv[1]
calls = {'provider':0, 'consumer':0}
cache = {}
statuses = []
for index in range(2):
    port = 'other' if mode=='port' and index else 'data'
    type_id = 'case.other' if mode=='type_id' and index else 'case.data'
    rule_id = 'other_consumer' if mode=='rule_id' and index else 'consumer'
    resources = {'provider':RuleDescriptor('provider', outputs={'value':type_id}),
        rule_id:RuleDescriptor(rule_id, inputs={port:type_id}, scope='call' if mode=='call_scope' else 'source',
            params_schema={'limit':{'type':'integer'}},params_defaults={'limit':index if mode=='params' else 1})}
    descriptor = RulesetDescriptor('case.identity', (RuleCall('provider','provider'),RuleCall('consumer',rule_id)),
        (RuleRelation('consumer','provider','requires',bindings={port:'value'}),))
    def provider(context, inputs, params):
        calls['provider'] += 1
        return RuleResult({'value':RuleRecord(type_id,{'value':7})})
    def consumer(context, inputs, params):
        calls['consumer'] += 1
        return RuleResult()
    identity = {} if mode=='no_source_identity' else {'source_identity':('file-'+str(index)) if mode=='source' else 'file'}
    context = RuleContext(subject=identity, target='javascript' if mode=='target' and index else 'python',
                          phase='import' if mode=='phase' and index else 'static')
    result = execute_rule_plan(compile_ruleset(descriptor,rules=resources),context,
        handlers={'provider':provider,rule_id:consumer},source_cache=cache)
    statuses.append(result.status)
print(json.dumps({'statuses':statuses, **calls}))
'''

CONTRIBUTIONS_PROBE = r'''
import json
from collections import Counter
from unittest.mock import patch
from vibeflow.targets.python.sdk import Plugin, ruleset
from vibeflow.core.rules import RulesetDescriptor
from vibeflow.core.descriptors.contributions import PluginContributions, ResourceDeclaration, ResourceOrigin, ResourceOwner, compose_contributions, contribution_facts

resource = ruleset(id='case.fixed', calls=())
counts = Counter()
original = RulesetDescriptor.to_dict
phase = 'unknown'
def counted(self):
    counts[phase] += 1
    return original(self)
with patch.object(RulesetDescriptor, 'to_dict', counted):
    phase = 'definition'; plugin = Plugin(id='case.plugin', resources=[resource])
    phase = 'contributions'; first = plugin.contributions({'items':[{'value':1}]}); second = plugin.contributions({'items':[{'value':2}]})
    phase = 'bindings'; bindings = plugin.bindings()
    phase = 'compose'; first_catalog = compose_contributions((first,)); second_catalog = compose_contributions((second,))
    phase = 'facts'; facts = contribution_facts(first_catalog)
try:
    first.config['items'][0]['value'] = 99
except TypeError:
    immutable = True
else:
    immutable = False
class ForgedDescriptor:
    id = 'case.forged'
    def to_dict(self):
        return {'kind':'ruleset', 'id':self.id, 'calls':[]}
invalid = {
    'raw_entry': (object(),),
    'wrong_origin': (ResourceDeclaration(resource.descriptor,ResourceOrigin(ResourceOwner("plugin", 'other.plugin'),'decl.py')),),
    'wrong_descriptor': (ResourceDeclaration(ForgedDescriptor(),ResourceOrigin(ResourceOwner("plugin", 'case.plugin'),'decl.py')),),
    'duplicate': (ResourceDeclaration(resource.descriptor,ResourceOrigin(ResourceOwner("plugin", 'case.plugin'),'first.py')),
                  ResourceDeclaration(resource.descriptor,ResourceOrigin(ResourceOwner("plugin", 'case.plugin'),'second.py'))),
}
checks = {}
for name, entries in invalid.items():
    try:
        PluginContributions('case.plugin',entries)
    except (TypeError,ValueError) as error:
        checks[name] = {'rejected':True, 'message':str(error), 'code':getattr(error,'code',''),
                        'origins':getattr(error,'details',{}).get('origins',{})}
    else:
        checks[name] = {'rejected':False}
print(json.dumps({'counts':dict(counts), 'internal_projections':sum(value for key,value in counts.items() if key!='facts'),
    'facts_projections':counts['facts'], 'facts_resources':len(facts['declarations']),
    'fixed_resources_same':first.resources == second.resources,
    'descriptor_shared':first.resources[0].descriptor is second.resources[0].descriptor,
    'catalogs_distinct':first_catalog is not second_catalog,
    'immutable':immutable, 'config_values':[first.config['items'][0]['value'],second.config['items'][0]['value']],
    'invalid':checks}))
'''

CLI_PROJECTION_PROBE = r'''
import contextlib, io, json, sys
from pathlib import Path
from unittest.mock import patch
from vibeflow.core.rules import RuleRecord
from vibeflow.tooling.application.cli import main
counts = {'cache':0, 'diagnostic':0, 'final':0}
original = RuleRecord.to_dict

def counted(self):
    caller = sys._getframe(1)
    category = 'final'
    while caller is not None:
        if caller.f_code.co_name == '_key':
            category = 'cache'
            break
        if caller.f_code.co_filename.endswith('/quality/rule_adapter.py'):
            category = 'diagnostic'
            break
        caller = caller.f_back
    counts[category] += 1
    return original(self)
stdout, stderr = io.StringIO(), io.StringIO()
with patch.object(RuleRecord,'to_dict',counted), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
    code = main(['validate','--workspace','../vibeflow_config.jsonc','--config','workflow.jsonc','--json'])
Path('validate.stdout.txt').write_text(stdout.getvalue())
Path('validate.stderr.txt').write_text(stderr.getvalue())
payload = json.loads(stdout.getvalue())
findings = [item for key in ('errors','warnings') for item in payload.get(key,[])]
observations = [json.loads(line) for line in Path('record.marker').read_text().splitlines()] if Path('record.marker').exists() else []
print(json.dumps({'cli_exit_code':code, 'status':payload['status'], 'projections':counts,
    'findings':[{'code':item.get('rule_id',item.get('code')), 'severity':item.get('severity'),
                 'calls':item.get('details',{}).get('calls',[]), 'location':item.get('source_location',{})}
                for item in findings], 'observations':observations}))
'''
