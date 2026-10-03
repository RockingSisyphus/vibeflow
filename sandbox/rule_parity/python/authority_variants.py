"""Invalid declaration shape is compared with the old authority at real CLI."""
from pathlib import Path
from copy import deepcopy
import runpy

_api=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))
case,legacy_contract,declaration_error=(_api[name] for name in ("case","legacy_contract","declaration_error"))


def case_specs():
    cases=[]
    for field in ("type_key","display_name","category","description","version"):
        cases.append(case("metadata."+field+"_empty", "Empty metadata field "+field, "declaration-shapes",
            node_fields={field:""},code="NODE.METADATA.NODE_INFO_"+field.upper(),expect=declaration_error(),
            classification="approved_change" if field=="category" else "preserved",
            notes="Approved migration: Node category is removed; current declarations reject the obsolete field before loading implementations." if field=="category" else ""))
    for field in ("type_key","display_name","category","description","version","flow_kind"):
        cases.append(case("metadata."+field+"_non_string", "Metadata field must be a string: "+field, "declaration-shapes",
            node_fields={field:1},code="NODE.FLOW_KIND.MISSING" if field=="flow_kind" else "NODE.METADATA.NODE_INFO_"+field.upper(),expect=declaration_error(),
            classification="approved_change" if field=="category" else "preserved",
            notes="Approved migration: Node category is removed; current declarations reject the obsolete field before loading implementations." if field=="category" else ""))
    cases.extend([
        case("metadata.type_mismatch","Declared type disagrees with requested type","declaration-shapes",node_fields={"type_key":"parity.other"},code="NODE.METADATA.TYPE_MISMATCH",expect=declaration_error()),
        case("metadata.flow_invalid","Invalid native flow kind","declaration-shapes",node_fields={"flow_kind":"invented"},code="NODE.FLOW_KIND.INVALID",expect=declaration_error()),
        case("metadata.external_non_bool","External metadata must be boolean","declaration-shapes",node_fields={"external":"yes"},code="NODE.EXTERNAL.INVALID",expect=declaration_error()),
        case("metadata.normal","Canonical metadata normal neighbour","declaration-shapes"),
    ])
    requirement={"type":"demo.in","cardinality":"optional_one","display_name":"Input"}
    provider={"key":"demo.out","type":"demo.out","display_name":"Result"}
    bad_shapes=[
        ("requires_scalar",{"requires":"bad"},legacy_contract(requires="'bad'"),"CONTRACT_REQUIREMENT_LIST"),
        ("requires_item",{"requires":[1]},legacy_contract(requires="(1,)"),"CONTRACT_REQUIREMENT_LIST"),
        ("provides_scalar",{"provides":"bad"},legacy_contract(provides="'bad'"),"CONTRACT_PROVIDER_LIST"),
        ("provides_item",{"provides":[1]},legacy_contract(provides="(1,)"),"CONTRACT_PROVIDER_LIST"),
        ("duplicate_requirements",{"requires":[requirement,requirement],"input_semantics":{"demo.in":["input"]}},legacy_contract(requires="(DataRequirement('demo.in','optional_one',display_name='Input'),DataRequirement('demo.in','optional_one',display_name='Input'))",input_semantics="{'demo.in':('input',)}"),"CONTRACT_DUPLICATE_REQUIREMENT_TYPE"),
    ]
    for name,contract,expression,code in bad_shapes:
        cases.append(case("contract."+name,name,"declaration-shapes",contract=contract,legacy_contract_expression=expression,code="NODE.CONTRACT."+code,expect=declaration_error()))
    for field,value in (("type",""),("cardinality","invalid"),("display_name","")):
        invalid={**requirement,field:value}
        expression=f"(DataRequirement({invalid['type']!r},{invalid['cardinality']!r},display_name={invalid['display_name']!r}),)"
        cases.append(case("contract.requirement_"+field,"Bad requirement "+field,"declaration-shapes",contract={"requires":[invalid],"input_semantics":{invalid["type"]:["input"]}},
            legacy_contract_expression=legacy_contract(requires=expression,input_semantics=repr({invalid["type"]:("input",)})),code="NODE.CONTRACT.CONTRACT_REQUIREMENT_SHAPE",expect=declaration_error()))
    for field in ("key","type","display_name"):
        invalid={**provider,field:""}
        expression=f"(DataProvider({invalid['key']!r},{invalid['type']!r},display_name={invalid['display_name']!r}),)"
        cases.append(case("contract.provider_"+field,"Bad provider "+field,"declaration-shapes",contract={"provides":[invalid],"output_semantics":{invalid["key"]:["output"]}},
            legacy_contract_expression=legacy_contract(provides=expression,output_semantics=repr({invalid["key"]:("output",)})),code="NODE.CONTRACT.CONTRACT_PROVIDER_SHAPE",expect=declaration_error()))
    cases.append(case("contract.requirement_valid","Optional valid requirement neighbour","declaration-shapes",contract={"requires":[requirement],"input_semantics":{"demo.in":["input"]}}))
    for name,value,expression in (("scalar",1,"1"),("value_scalar",{"demo.out":1},"{'demo.out':1}"),("value_blank",{"demo.out":[""]},"{'demo.out':('',)}"),("value_number",{"demo.out":[1]},"{'demo.out':(1,)}")):
        cases.append(case("semantics."+name,"Malformed output semantics "+name,"declaration-shapes",contract={"output_semantics":value},legacy_contract_expression=legacy_contract(output_semantics=expression),code="NODE.CONTRACT.CONTRACT_SEMANTICS",expect=declaration_error()))
    cases.append(case("semantics.normal","Valid input/output semantics neighbour","declaration-shapes"))
    for name,value in (("blank", ""),("number", 1)):
        cases.append(case("semantics.input_value_"+name,"Malformed input semantics "+name,"declaration-shapes",
            contract={"requires":[requirement],"input_semantics":{"demo.in":[value]}},
            legacy_contract_expression=legacy_contract(requires="(DataRequirement('demo.in','optional_one',display_name='Input'),)",input_semantics=repr({"demo.in":(value,)})),
            code="NODE.CONTRACT.CONTRACT_SEMANTICS",expect=declaration_error()))
    for name,options,code in (
        ("invalid_info",{"legacy_info_expression":"1"},"MISSING_NODE_INFO"),
        ("missing_contract",{"baseline_contract":False},"MISSING_CONTRACT"),
        ("invalid_contract",{"legacy_contract_expression":"1"},"MISSING_CONTRACT"),
    ):
        cases.append(case("authority."+name,"Legacy class authority is replaced: "+name,"declaration-authority",**options,
            code="NODE.CONTRACT."+code,classification="approved_change",expect={"variants":{"current":{"should_accept":True,"codes":[]}}},
            notes="The current resource declaration remains complete and valid. Only legacy implementation-class metadata is absent or malformed; canonical authority migration explicitly permits ignoring that class metadata."))
    signatures=[("varargs","self,inputs,params,*extra",False),("kwargs","self,inputs,params,**extra",False),
        ("keyword_only","self,inputs,*,params",False),("wrong_order","self,params,inputs",False),
        ("extra_default","self,inputs,params,extra=1",False),("posonly","self,inputs,params,/",True),
        ("defaults","self,inputs=None,params=None",True),("normal","self,inputs,params",True)]
    for name,arguments,allowed in signatures:
        source=f'class DemoNode:\n    def run_pure({arguments}):\n        return {{"demo.out":1}}\n'
        cases.append(case("signature."+name,"run_pure signature "+name,"node-interface",source=source,code=None if allowed else "NODE.CONTRACT.RUN_PURE_SIGNATURE"))
    for name,args in (("default_self","self=1"),("keyword_only","self,*,value=1"),("varargs","self,*values"),("kwargs","self,**values")):
        source=f'class DemoNode:\n    def __init__({args}):\n        pass\n    def run_pure(self,inputs,params):\n        return {{"demo.out":1}}\n'
        cases.append(case("signature.init_"+name,"__init__ signature "+name,"node-interface",source=source,code="NODE.CONTRACT.INIT_SIGNATURE"))
    cases.append(case("signature.init_normal","Parameterless initializer neighbour","node-interface",source='class DemoNode:\n    def __init__(self):\n        pass\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'))
    for name,assignment,bad in (("public_lambda","public=lambda value:value",True),("public_value","public=1",False)):
        cases.append(case("signature."+name,"Public class member "+name,"node-interface",source='class DemoNode:\n    '+assignment+'\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n',code="NODE.CONTRACT.PUBLIC_CALLABLE" if bad else None))
    fragile={"requires_scalar","requires_item","provides_scalar","provides_item","semantics.scalar","semantics.value_scalar"}
    transports=[]
    for spec in cases:
        suffix=spec["id"].removeprefix("python.variant.contract.")
        suffix=spec["id"].removeprefix("python.variant.") if ".semantics." in spec["id"] else suffix
        if suffix not in fragile:
            continue
        transport=deepcopy(spec)
        transport["id"]+=".cli_transport"
        transport["classification"]="baseline_limitation"
        transport["process_exception_observation"]=True
        transport["expected"]={"should_accept":False,"status":"ERROR","codes":[],"metrics":{"transport":"uncaught_exception","exit_code":1},
            "message_contains":"contract_payload", "variants":{"current":{"status":"ERROR","codes":[{"code":"NODE.INSPECT.LOAD_ERROR","severity":"error"}],"metrics":{"exit_code":1},"message_contains":""}}}
        transport["notes"]="The original formal inspect-node CLI crashes while serializing the invalid contract. Public validate_node_class separately proves the original active judgment; current CLI emits a regular declaration error."
        transports.append(transport)
        spec["entrypoints"]={"baseline":"target.validate_node_class","current":"cli.inspect-node"}
        spec["notes"]="The baseline public validator is used because formal inspect-node contract serialization raises before returning JSON. Current uses the canonical declaration CLI rejection; this is an explicitly different transport boundary."
    return [*cases,*transports]
