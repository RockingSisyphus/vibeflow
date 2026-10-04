"""All public shapes and resource colors in Architecture, Mermaid and browser SVG."""
from resource_support import project,documents,observe,KINDS,IDS,mutate_presentation,rgb,config,cli

SHAPES=("rect","rounded","stadium","diamond","lean-r","lean-l","fr-rect","cyl","doc","hex","cloud","circle","dbl-circ","trap-b")


def evidence(actual,architecture,mermaid,browser,kind,fields,*,override=False):
    key=kind+":"+IDS[kind]
    resource=architecture.get("implementation_graph",{}).get("resources",{}).get(key,{})
    values=resource.get("effective_presentation",{}).get("values",{})
    sources=resource.get("effective_presentation",{}).get("sources",{})
    shape="diam" if fields.get("shape")=="diamond" else fields.get("shape",values.get("shape"))
    candidates=[node for node in browser.get("nodes",[]) if kind+": "+IDS[kind] in node["text"]]
    # Browser text can concatenate rows in native SVG text labels.
    if not candidates:candidates=[node for node in browser.get("nodes",[]) if kind+": "+IDS[kind] in node["text"].replace("status:"," status:")]
    shapes=[item for node in candidates for item in node["shapes"]]
    geometry=fields.get("shape",values.get("shape"))
    if geometry in {"rect","rounded"}:
        shape_matches=any(item["tag"]=="rect" and (float(item.get("rx") or 0)>0)==(geometry=="rounded") for item in shapes)
    elif geometry in {"circle","dbl-circ"}:
        shape_matches=sum(item["tag"]=="circle" for item in shapes)==(2 if geometry=="dbl-circ" else 1)
    elif geometry in {"diamond","lean-r","lean-l","fr-rect","hex","trap-b"}:
        count=10 if geometry=="fr-rect" else 6 if geometry=="hex" else 4
        shape_matches=any(item["tag"]=="polygon" and len((item["points"] or "").split())==count for item in shapes)
    else:shape_matches=any(item["tag"]=="path" and item["d"] for item in shapes)
    actual["metrics"].update(architecture_shape=values.get("shape"),architecture_fill=values.get("fill"),
        presentation_origin=sources.get("fill"),mermaid_shape=("shape: "+str(shape)) in mermaid,
        browser_resource_count=len(candidates),browser_fill=any(item["fill"]==rgb(fields["fill"]) for item in shapes),
        browser_stroke=any(item["stroke"]==rgb(fields["stroke"]) for item in shapes),
        browser_text=any(label["fill"]==rgb(fields["text"]) or label["color"]==rgb(fields["text"]) for node in candidates for label in node["labels"]),
        browser_shape=bool(shape_matches),architecture_stroke=values.get("stroke"),architecture_text=values.get("text"),
        browser_geometry=bool(shapes) and all(item["width"]>0 and item["height"]>0 for item in shapes),
        icon_visible=all(fields.get("icon", "") in node["text"] for node in candidates))
    return {"architecture_shape":shape,"architecture_fill":fields["fill"],"presentation_origin":"call" if override else kind,
        "mermaid_shape":True,"browser_resource_count":1,"browser_fill":True,"browser_stroke":True,"browser_text":True,
        "browser_shape":True,"architecture_stroke":fields["stroke"],"architecture_text":fields["text"],
        "browser_geometry":True,"icon_visible":True,"browser_exit_code":0}


def run_cases(work,toolchain):
    rows=[]
    for kind in KINDS:
        for shape in SHAPES:
            case=f"display.{kind}.shape.{shape}";root=project(work/case,toolchain=toolchain)
            fields={"fill":"#bedcfa","stroke":"#346789","text":"#234567","shape":shape,"icon":"R"}
            mutate_presentation(root,kind,fields)
            actual,architecture,mermaid,browser=documents(root,screenshot=shape in {"cloud","diamond","cyl"})
            expected=evidence(actual,architecture,mermaid,browser,kind,fields)
            rows.append(observe(case,"resource-display",actual,metrics=expected))
        for mode in ("colours","override"):
            case=f"display.{kind}.{mode}";root=project(work/case,toolchain=toolchain)
            fields={"fill":"#aaccee","stroke":"#225588","text":"#123789","shape":"hex","icon":"Colour"}
            mutate_presentation(root,kind,fields)
            override=mode=="override"
            if override:
                fields={**fields,"fill":"#ffeebb"}
                if kind=="node":config(root,lambda x:x["pipeline"]["nodes"][1].update(style={"fill":fields["fill"]}))
                elif kind=="host_extension":config(root,lambda x:x["host_extensions"][0].update(style={"fill":fields["fill"]}))
                elif kind=="plugin":config(root,lambda x:x["plugins"][0].update(style={"fill":fields["fill"]}))
                else:config(root,lambda x:x.update(base_lib={"modules":[{"id":"demo.math","style":{"fill":fields["fill"]}}]}))
            actual,architecture,mermaid,browser=documents(root,screenshot=True)
            # Node invocation colors override its declaration in the Workflow,
            # while the resource's implementation declaration keeps its default.
            graph_override=override and kind!="node"
            expected=evidence(actual,architecture,mermaid,browser,kind,fields if graph_override or not override else {**fields,"fill":"#aaccee"},override=graph_override)
            if kind=="node" and override:
                calls=[node for node in browser.get("nodes",[]) if "type_used: demo.model" in node["text"]]
                actual["metrics"]["call_override_fill"]=any(item["fill"]==rgb(fields["fill"]) for node in calls for item in node["shapes"])
                expected["call_override_fill"]=True
            rows.append(observe(case,"resource-display",actual,metrics=expected))
    from resource_display_extra import run_cases as additional
    rows.extend(additional(work,toolchain))
    return rows
