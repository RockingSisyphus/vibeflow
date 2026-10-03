"""Compact specifications share assertions, never baseline implementation APIs."""

from textwrap import indent


def case(name, title, family, *, body='return {"demo.out": 1}', source=None, code=None, severity="error", accept=None, **options):
    expected = {"should_accept": code is None or severity != "error" if accept is None else accept,
        "codes": [] if code is None else [{"code": code, "severity": severity}]}
    expected.update(options.pop("expect", {}))
    return {"id": "python.variant." + name, "title": title, "family": family,
        "source": source or 'class DemoNode:\n    def run_pure(self, inputs, params):\n'+indent(body,"        ")+"\n",
        "expected":expected, **options}


def legacy_contract(**overrides):
    fields={"requires":"()", "provides":"(DataProvider('demo.out','demo.out',display_name='Result'),)",
        "input_semantics":"{}", "output_semantics":"{'demo.out':('result value',)}", "examples":"({'inputs':{},'params':{}},)"}
    fields.update(overrides)
    return "NodeContract("+",".join(name+"="+value for name,value in fields.items())+")"


def declaration_error():
    return {"variants":{"current":{"codes":[{"code":"NODE.INSPECT.LOAD_ERROR","severity":"error"}]}}}
