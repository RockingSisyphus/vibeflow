/* An application supplies its own queue/store and consumes public results. */
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [entry,requestFile]=process.argv.slice(2);
const request=JSON.parse(readFileSync(requestFile,'utf8'));
const workflow=await import(pathToFileURL(entry).href);
const audit=[];
const events=[];
const initial={...request.initial};
const received=[],sent=[];
if(request.session){
 const records=new Map([['held','released']]);
 initial.app_session={
  clock:{async now(){return '2026-01-02T03:04:05Z';}},
  storage:{async read(value){return {value:records.get(value.key)};},async get(value){return records.get(value.key);}},
  audit:{async record(value){audit.push(value);return {accepted:true};}},
 };
}
if(request.initial_factory==='formula'){
 const messages=[{value:request.formula_value}];
 initial.app_session={queue:{async receive(value){received.push({...value});
  if(!messages.length)throw Error('application queue is empty');return messages.shift();},
  send(value){sent.push({...value});return null;}}};
}
try{
 const execute=request.mode==='async'?workflow.runWorkflowAsync:workflow.runWorkflow;
 const options={...request.options};
 if(request.observe_business)options.onTrace=event=>events.push(event);
 const result=execute(initial,options);
 const asynchronous=!!result?.then;
 const output=await result;
 console.log('RESULT '+JSON.stringify({output,asynchronous,audit,...(request.observe_business?{events}:{}),
  ...(request.initial_factory==='formula'?{application_ports:{received,sent}}:{})}));
}catch(error){
 console.log('FAILURE '+JSON.stringify({code:error.code,message:error.message,
  workflowId:error.workflowId,nodePath:error.nodePath,blockPath:error.blockPath}));
 process.exitCode=1;
}
