from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
repo=Path('/home/rockingsisyphus/projects/VibeFlow')
base=repo/'sandbox/resources/python'
work=Path(tempfile.mkdtemp(prefix='vibeflow-wide-python-cli-'))
cases=[]
for statement,label in [('from sys import stdout','sys_stdout'),('from io import open as file_open','io_open'),('from http import client','http_client')]:
 for kind in ['base_lib','plugin']:
  cases.append((label+'-'+kind,kind,statement))
cases.extend([(name+'-'+kind,kind,code) for name,code in [('sys_stdout_attribute','import sys\ndef get_stream():\n    return sys.stdout\n'),('sys_path_assignment','import sys\ndef mutate():\n    sys.path = []\n')] for kind in ['base_lib','plugin']])
cases.extend([('local_identity-plugin','plugin','local_identity'),('local_write-plugin','plugin','local_write'),('local_write-base_lib','base_lib','local_write')])
out=[]
for name,kind,text in cases:
 root=work/name
 shutil.copytree(base,root,ignore=shutil.ignore_patterns('ARCHITECTURE*','__pycache__','reports','runs'))
 (root/'vibeflow_project.jsonc').write_text('{"project_target":"python"}\n')
 # The isolated library review has no caller effect selection to mask it.
 p=root/'node_resource.py'; p.write_text(p.read_text().replace('rulesets=["vibeflow.process"]','rulesets=[]'))
 target=root/('math_support.py' if kind=='base_lib' else 'plugin_support.py')
 if text in {'local_write','local_identity'}:
  if kind=='base_lib': target.write_text('def write(value):\n    return value\ndef add(left,right):\n    return write(left) + right\n')
  else: target.write_text('def write(value):\n    return value\n\nclass Runtime:\n    def before_node(self,node_id,node_type,inputs):\n        write(1)\n    def after_node(self,node_id,node_type,outputs):\n        pass\n    def dispose(self):\n        pass\n')
 else: target.write_text(text+'\n'+target.read_text())
 if text=='local_identity': target.write_text(target.read_text().replace('write','identity'))
 result=subprocess.run([sys.executable,'-B','-m','vibeflow','validate','--workspace',str(root/'vibeflow_config.jsonc'),'--config',str(root/'workflow.jsonc'),'--json'],cwd=repo,env={**os.environ,'PYTHONPATH':str(repo/'src'),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=30)
 (work/f'{name}.json').write_text(result.stdout)
 (work/f'{name}.stderr').write_text(result.stderr)
 try: data=json.loads(result.stdout)
 except Exception: data={}
 row={'case':name,'exit':result.returncode,'status':data.get('status'),'errors':[{'code':f.get('code',f.get('rule_id')),'definition_id':f.get('definition_id'),'message':f.get('message'),'source_location':f.get('source_location')} for f in data.get('errors',[])]}
 out.append(row)
 print(json.dumps(row))
Path('/tmp/vibeflow-wide-python-cli-branch-probes.json').write_text(json.dumps({'work':str(work),'observations':out},indent=2))
