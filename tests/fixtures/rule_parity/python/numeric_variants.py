"""Node source byte warning and contract width boundaries."""
from pathlib import Path
import runpy

case=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))["case"]


def case_specs():
    cases=[]
    for count,warn,bad in ((220,500,True),(100,1500,False)):
        cases.append(case("numeric.byte_warning_"+str(count),"UTF-8 byte warning neighbour "+str(count),"node-metrics",
            body='text="'+'界'*count+'"\nreturn {"demo.out":text}',code="NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT" if bad else None,
            severity="warning",policy={"node_source":{"max_bytes":3000,"warn_bytes":warn}},
            expect={} if bad else {"forbidden_codes":["NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT"]}))
    for width in (10,11):
        providers=[{"key":f"demo.value_{i}","type":f"demo.value_{i}","display_name":"Value"} for i in range(width)]
        body="return "+repr({item["key"]:1 for item in providers})
        contract={"provides":providers,"output_semantics":{item["key"]:["value"] for item in providers}}
        cases.append(case("numeric.contract_width_"+str(width),"Fixed contract width boundary "+str(width),"node-metrics",body=body,contract=contract,
            code="NODE.MAINTAINABILITY.WIDE_CONTRACT" if width==11 else None,severity="warning",
            expect={} if width==11 else {"forbidden_codes":["NODE.MAINTAINABILITY.WIDE_CONTRACT"]}))
    for maximum in (2,3):
        providers=[{"key":f"demo.value_{i}","type":f"demo.value_{i}","display_name":"Value"} for i in range(3)]
        cases.append(case("numeric.contract_key_limit_"+str(maximum),"Configured contract key threshold "+str(maximum),"node-metrics",
            body="return "+repr({item["key"]:1 for item in providers}),contract={"provides":providers,"output_semantics":{item["key"]:["value"] for item in providers}},
            code="NODE.MAINTAINABILITY.COMPLEXITY_MAX_CONTRACT_KEYS" if maximum==2 else None,policy={"complexity":{"max_contract_keys":maximum}}))
    return cases
