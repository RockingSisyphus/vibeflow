"""Invalid styles, status provenance and nonpublication of failed formal reviews."""
import hashlib

from resource_support import project,cli,documents,observe,KINDS,IDS,PARTS,mutate_presentation,config,rgb,replace,display_resource,display_nodes,preview_style_matches,preview_nodes


def run_cases(work,toolchain,*,kinds=KINDS,state_kinds=("host_extension","plugin_declaration","node_external")):
    rows=[]
    for kind in kinds:
        for field,value in (("fill","blue"),("stroke","#abc"),("text",True),("shape","triangle"),("icon",""),("fill","#fee2e2")):
            case=f"display.{kind}.invalid.{field}.{str(value).replace('#','')}";root=project(work/case,toolchain=toolchain)
            mutate_presentation(root,kind,{field:value})
            actual=cli(root,"inspect-resources",name="invalid")
            rows.append(observe(case,"resource-display",actual,accept=False,code="DESCRIPTOR.INVALID"))
        for override in (False,True):
            case=f"display.{kind}.warning.{'override' if override else 'status'}";root=project(work/case,toolchain=toolchain)
            path=root/PARTS[kind];text=path.read_text();path.write_text(text+"// reviewed support\n"*(450-len(text.splitlines())))
            if override:
                if kind=="node":config(root,lambda x:x["pipeline"]["nodes"][1].update(style={"fill":"#ffeebb"}))
                elif kind=="host_extension":config(root,lambda x:x["host_extensions"][0].update(style={"fill":"#ffeebb"}))
                elif kind=="plugin":config(root,lambda x:x["plugins"][0].update(style={"fill":"#ffeebb"}))
                else:config(root,lambda x:x.update(base_lib={"modules":[{"id":"demo.math","style":{"fill":"#ffeebb"}}]}))
            actual,architecture,_,browser=documents(root,name="warning",screenshot=True)
            resource=display_resource(architecture,kind)
            presentation=resource.get("effective_presentation",{})
            fields=presentation.get("values",{});sources=presentation.get("sources",{})
            nodes=display_nodes(browser,kind)
            source_resource=architecture.get("implementation_graph",{}).get("resources",{}).get(kind+":"+IDS[kind],{})
            actual["metrics"].update(marker="warning" in source_resource.get("markers",()),
                diagnostic=any(item.get("severity")=="warning" for item in source_resource.get("diagnostics",())),
                fill_origin=sources.get("fill"),status_fill=fields.get("fill"),
                matches_svg=any(shape["fill"]==rgb(fields["fill"]) for node in nodes for shape in node["shapes"]),
                matches_preview=preview_style_matches(browser,architecture,kind))
            rows.append(observe(case,"resource-display",actual,metrics={"marker":True,"diagnostic":True,
                "fill_origin":"call" if override else "status",
                "status_fill":"#ffeebb" if override else "#fef3c7","matches_svg":True,"matches_preview":True,"browser_exit_code":0,"mermaid_exit_code":0}))
        case=f"display.{kind}.failed_review_keeps_previous";root=project(work/case,toolchain=toolchain)
        before,_,_,_=documents(root,name="formal")
        svg=root/"evidence/formal.svg";document=root/"ARCHITECTURE.jsonc"
        if before["metrics"]["exit_code"] != 0 or not svg.is_file() or not document.is_file():
            before["metrics"].update(initial_review=before["metrics"]["exit_code"],artifacts_preserved=False,
                                      setup_failed=True,missing_artifacts=[str(path) for path in (svg,document) if not path.is_file()])
            rows.append(observe(case,"resource-display",before,accept=False,
                code="NODE.PURITY.SOURCE_TOO_LARGE" if kind=="node" else "BASE_LIB.SOURCE.MAX_LINES",
                metrics={"initial_review":0,"artifacts_preserved":True}))
            continue
        originals=[hashlib.sha256(path.read_bytes()).hexdigest() for path in (svg,document)]
        path=root/PARTS[kind];text=path.read_text();path.write_text(text+"// invalid support\n"*(501-len(text.splitlines())))
        actual=cli(root,"review",name="failed-review",extra=["--output",svg])
        actual["metrics"].update(initial_review=before["metrics"]["exit_code"],artifacts_preserved=originals==[hashlib.sha256(path.read_bytes()).hexdigest() for path in (svg,document)])
        rows.append(observe(case,"resource-display",actual,accept=False,code="NODE.PURITY.SOURCE_TOO_LARGE" if kind=="node" else "BASE_LIB.SOURCE.MAX_LINES",metrics={"initial_review":0,"artifacts_preserved":True}))
    for kind in state_kinds:
        case=f"display.{kind}.state";root=project(work/case,toolchain=toolchain)
        if kind=="host_extension":config(root,lambda x:x["host_extensions"][0].update(status="planned"))
        elif kind=="plugin_declaration":config(root,lambda x:x["plugins"].append({"id":"pending","status":"planned","type":"runtime","targets":["node","browser"],"display_name":"Pending","description":"Not loaded","source":{"kind":"file","ref":"never-loaded.ts"}}))
        else:replace(root,"node.ts",'type_key:"demo.model",','type_key:"demo.model",external:true,')
        actual,architecture,_,browser=documents(root,name="status",screenshot=True)
        key="node:demo.model" if kind=="node_external" else "plugin_declaration:pending" if kind=="plugin_declaration" else "host_extension:demo.host"
        resource=architecture.get("implementation_graph",{}).get("resources",{}).get(key,{})
        view="flow" if kind=="node_external" else "plugin" if kind=="plugin_declaration" else kind
        cards=preview_nodes(browser,architecture,"node") if kind=="node_external" else [
            card for card in browser.get("preview",{}).get("views",{}).get(view,()) if card["id"]==key]
        values=(display_resource(architecture,"node") if kind=="node_external" else resource).get("effective_presentation",{}).get("values",{})
        actual["metrics"].update(marker=("external" if kind=="node_external" else "planned") in resource.get("markers",()),
            fill_origin=resource.get("effective_presentation",{}).get("sources",{}).get("fill"),has_sources=bool(resource.get("sources")),
            preview_status=len(cards)==1 and ("外部依赖" if kind=="node_external" else "计划 · 尚未实现") in cards[0]["text"],
            preview_status_fill=len(cards)==1 and cards[0]["outline"]["fill"]==rgb(values["fill"]))
        rows.append(observe(case,"resource-display",actual,metrics={"marker":True,"fill_origin":"status","has_sources":kind!="plugin_declaration","browser_exit_code":0,
            "preview_status":True,"preview_status_fill":True}))
    return rows
