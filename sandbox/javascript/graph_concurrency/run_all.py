"""Public AOT CLI acceptance for twelve explicit ordinary graph branches."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
sys.dont_write_bytecode=True
FIXTURE=Path(__file__).resolve().parent
ROOT=FIXTURE.parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from tests.fixtures.support.addition_sandboxes import cli,workspace


def run(work,toolchain,puppeteer=None):
    workspace(FIXTURE,work,toolchain)
    result=json.loads(cli(['build','--workspace',work/'vibeflow_config.jsonc','--config',work/'project/configs/concurrent.jsonc',
        '--out-dir',work/'dist','--target','node','--profile','single-esm']).stdout)
    entry=Path(result['entry'])
    assert entry.is_file(),entry
    script=work/'probe.mjs'
    script.write_text('import {runWorkflowAsync} from '+json.dumps(entry.as_uri())+''';
const rows=[];
for(let round=0;round<2;round++) {
 const trace=[];const outputs=await runWorkflowAsync({scenario:'success'},{trace:'full',onTrace:event=>trace.push(event)});
 if(JSON.stringify(outputs.report)!==JSON.stringify(Array.from({length:12},(_,i)=>i)))throw Error(JSON.stringify(outputs));
 const completed=trace.filter(event=>event.kind==='node_end');
 rows.push({round,outputs,completed:completed.length});
}
console.log(JSON.stringify(rows));
''')
    done=subprocess.run(['node',str(script)],capture_output=True,text=True,timeout=30)
    assert done.returncode==0,done.stdout+done.stderr
    observations=[{'execution':'node','status':'PASS','rounds':json.loads(done.stdout)}]
    if puppeteer:
        browser_build=json.loads(cli(['build','--workspace',work/'vibeflow_config.jsonc','--config',work/'project/configs/concurrent.jsonc',
            '--out-dir',work/'browser-dist','--target','browser','--profile','single-esm']).stdout)
        browser_entry=Path(browser_build['entry'])
        from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
        from functools import partial
        from threading import Thread
        (work/'index.html').write_text('<!doctype html><title>Graph concurrency acceptance</title>')
        class Assets(SimpleHTTPRequestHandler):
            extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript'}
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Assets,directory=str(work)))
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            browser=work/'browser.mjs'
            browser.write_text('import {createRequire} from "node:module";import {pathToFileURL} from "node:url";\n'+
                'const require=createRequire('+json.dumps(str(puppeteer/'package.json'))+');\n'+
                'const {default:puppeteer}=await import(pathToFileURL(require.resolve("puppeteer")).href);\n'+
                'const browser=await puppeteer.launch({headless:true,executablePath:process.env.PUPPETEER_EXECUTABLE_PATH,args:["--no-sandbox","--disable-setuid-sandbox"]});\n'+
                'try{const page=await browser.newPage();await page.goto('+json.dumps(f'http://127.0.0.1:{server.server_port}/index.html')+');\n'+
                'const outputs=await page.evaluate(async path=>{const module=await import(path);return await module.runWorkflowAsync({scenario:"success"});},'+json.dumps('/'+browser_entry.relative_to(work).as_posix())+');\n'+
                'if(JSON.stringify(outputs.report)!==JSON.stringify(Array.from({length:12},(_,i)=>i)))throw Error(JSON.stringify(outputs));console.log(JSON.stringify(outputs));}finally{await browser.close();}')
            done=subprocess.run(['node',str(browser)],capture_output=True,text=True,timeout=60)
            assert done.returncode==0,done.stdout+done.stderr
            observations.append({'execution':'chromium','status':'PASS','outputs':json.loads(done.stdout)})
        finally:server.shutdown();server.server_close();thread.join()
    return {'status':'PASS','observations':observations}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',type=Path);parser.add_argument('--toolchain-root',type=Path,required=True);parser.add_argument('--puppeteer-root',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='vibeflow-native-graph-') as temporary:
        work=args.work_dir.resolve() if args.work_dir else Path(temporary);work.mkdir(parents=True,exist_ok=True)
        report=run(work,args.toolchain_root,args.puppeteer_root)
        (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('JavaScript ordinary graph concurrency: PASS')
if __name__=='__main__':main()
