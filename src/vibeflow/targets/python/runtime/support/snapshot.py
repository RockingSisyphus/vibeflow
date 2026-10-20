"""JSON storage for the finite set of native records used by Python AOT.

Unlike object pickles, this codec cannot import or instantiate arbitrary classes.
Host objects stay outside the artifact and are supplied when a run is created.
"""
from dataclasses import fields, is_dataclass
from collections.abc import Mapping

from vibeflow.core import flow, contracts, planned, compiler
from vibeflow.core.workflows import entries
from vibeflow.core.workflows import targets
from vibeflow.core.rules import models as rule_models
from vibeflow.core.rules.selection import models as selection_models


_RECORDS = {value.__module__ + '.' + value.__name__: value
    for module in (flow, contracts, planned, compiler, rule_models, selection_models, entries, targets)
    for value in vars(module).values() if isinstance(value, type) and is_dataclass(value)}


def encode_snapshot(value, *, relocate=lambda value: value):
    records, identities = [], {}

    def encode(item):
        if is_dataclass(item):
            identity = id(item)
            if identity in identities:
                return {'$ref': identities[identity]}
            name = type(item).__module__ + '.' + type(item).__name__
            if name not in _RECORDS:
                raise TypeError(f'unsupported Python AOT record: {name}')
            index = len(records)
            identities[identity] = index
            record = {'type': name, 'fields': {}}
            records.append(record)
            record['fields'] = {field.name: encode(
                relocate(getattr(item, field.name)) if field.name in {'project_root','root_path','source_path'}
                else getattr(item, field.name)) for field in fields(item)}
            return {'$ref': index}
        if isinstance(item, Mapping):
            return {'$mapping': [[key, encode(child)] for key,child in item.items()]}
        if isinstance(item, tuple):
            return {'$tuple': [encode(child) for child in item]}
        if isinstance(item, list):
            return [encode(child) for child in item]
        if item is None or isinstance(item, (str,int,float,bool)):
            return item
        raise TypeError(f'Python AOT cannot store live {type(item).__name__}; supply it as a runtime input or capability')

    root = encode(value)
    return {'root': root, 'records': records}


def decode_snapshot(value, *, relocate=lambda value: value):
    records = value['records']
    # GraphConfig definition tables may refer back to their containing graph.
    # Allocate the finite native records first, then restore these references.
    instances = [_RECORDS[record['type']].__new__(_RECORDS[record['type']]) for record in records]

    def decode(item):
        if isinstance(item, list):
            return [decode(child) for child in item]
        if not isinstance(item, dict):
            return item
        if set(item) == {'$ref'}:
            return instances[item['$ref']]
        if set(item) == {'$mapping'}:
            return {key:decode(child) for key,child in item['$mapping']}
        if set(item) == {'$tuple'}:
            return tuple(decode(child) for child in item['$tuple'])
        raise ValueError('invalid Python AOT native record')

    for instance,record in zip(instances,records):
        expected = {field.name for field in fields(instance)}
        if set(record['fields']) != expected:
            raise ValueError(f'invalid fields for {record["type"]}')
        for key,item in record['fields'].items():
            decoded = decode(item)
            object.__setattr__(instance,key,relocate(decoded) if key in {'project_root','root_path','source_path'} else decoded)
    for instance in instances:
        post_init = getattr(instance,'__post_init__',None)
        if post_init is not None:
            post_init()
    return decode(value['root'])
