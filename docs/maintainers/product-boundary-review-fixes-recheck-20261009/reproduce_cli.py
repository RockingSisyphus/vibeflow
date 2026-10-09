"""Reproduce this review's current CLI observations in saved minimal projects."""
import argparse,json,subprocess,sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--product",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    bootstrap="import sys,json;sys.path.insert(0,sys.argv[1]);from vibeflow.tooling.application.python.cli import main;raise SystemExit(main(json.loads(sys.argv[2])))"
    rows=[]
    for config in sorted((Path(__file__).resolve().parent/"fixtures").glob("*/vibeflow_config.jsonc")):
        argv=["validate","--workspace",str(config),"--config",str(config.parent/"workflow.jsonc"),"--json"]
        result=subprocess.run([sys.executable,"-I","-B","-c",bootstrap,str(args.product.resolve()),json.dumps(argv)],cwd=config.parent,capture_output=True,text=True,timeout=30)
        payload=json.loads(result.stdout)
        rows.append({"case":config.parent.name,"version":"current","exit":result.returncode,"status":payload.get("status"),"codes":[item.get("code",item.get("rule_id")) for item in payload.get("errors",())]})
    args.report.write_text(json.dumps(rows,indent=2)+"\n")
    print(json.dumps(rows,indent=2))

if __name__=="__main__":main()
