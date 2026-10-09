"""Known Node identity comes from the complete registry, never a naming trick."""


OTHER = 'class OtherNode:\n    _private=7\n    def run_pure(self, inputs, params):\n        return {}\n'


def _case(name, title, source, code=None, **options):
    expected = {"should_accept": code is None, "codes": [] if code is None else [{"code": code, "severity": "error"}],
        "located_codes": [] if code is None else [code]}
    expected.update(options.pop("expect", {}))
    return {"id": "python.coupling." + name, "title": title, "family": "node-coupling",
        "entrypoint": "target.validate_graph_health", "registered_other_node": True,
        "source": source, "expected": expected, **options}


def case_specs():
    method = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n'
    return [
        _case("import_registered_node", "Import an actual registered Node from a neutral implementation directory",
            'from implementations.other import OtherNode\n' + method, "NODE.METADATA.NODE_IMPORT", other_node_ref="implementations/other.py"),
        _case("direct_registered_node", "Directly invoke another actual registered Node",
            OTHER + 'class DemoNode:\n    def run_pure(self, inputs, params):\n        OtherNode().run_pure({}, {})\n        return {"demo.out": 1}\n', "NODE.METADATA.NODE_DIRECT_CALL"),
        _case("private_registered_node", "Read a private member of another actual registered Node",
            OTHER + 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": OtherNode._private}\n', "NODE.METADATA.NODE_INTERNAL_READ",
            classification="new_feature", expect={"variants": {"baseline": {"should_accept": True, "codes": [], "located_codes": [], "forbidden_codes": ["NODE.METADATA.NODE_INTERNAL_READ"]}}},
            notes="Baseline only treated NODE_INFO/CONTRACT attribute reads as Node internals; actual arbitrary private member reads were accepted. Current canonical registry identity rejects this extra case."),
        _case("ordinary_helper", "A ordinary helper is legal while another real Node remains registered",
            OTHER + 'def step(value):\n    return value+1\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": step(1)}\n',
            expect={"forbidden_codes": ["NODE.METADATA.NODE_IMPORT", "NODE.METADATA.NODE_DIRECT_CALL", "NODE.METADATA.NODE_INTERNAL_READ"]}),
    ]
