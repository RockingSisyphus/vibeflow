import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';

const [entry,countText,roundsText]=process.argv.slice(2),count=Number(countText),rounds=Number(roundsText);
const started=performance.now(),workflow=await import(pathToFileURL(entry).href),loadMs=performance.now()-started;
function invoke(module,input){
  const result=module.runWorkflow({number:input},{trace:'off'});
  assert.equal(result.number,input+count);
  return result;
}
const original=await readFile(entry,'utf8');
const hookPattern=/(function invokeRuntimeHookSync\([^)]*\) \{)/;
assert(hookPattern.test(original));
const fastEntry=entry+'.empty-hooks.mjs';
await writeFile(fastEntry,original.replace(hookPattern,'$1 if(root.runtimePlugins.length===0)return;'));
const fast=await import(pathToFileURL(fastEntry).href);
for(let i=0;i<10;i++){invoke(workflow,i);invoke(fast,i);}
const samples=[],emptyHookSamples=[];
for(let i=0;i<rounds;i++){
  const order=i%2===0?[[workflow,samples],[fast,emptyHookSamples]]:[[fast,emptyHookSamples],[workflow,samples]];
  for(const [module,values] of order){const before=performance.now();invoke(module,i);values.push(performance.now()-before);}
}
// Count another copy. Its instrumentation overhead is never used for latency.
let source=original;
const names=['createStaticWorkflowSync','prepareWorkflowInvocation','deepFreeze','runtimePluginSummary','definePlugin'];
const found=[];
for(const name of names){
  const pattern=new RegExp(`(function ${name}\\([^)]*\\) \\{)`);
  if(pattern.test(source)){
    source=source.replace(pattern,`$1 __aotProbeCounts[${JSON.stringify(name)}]=(__aotProbeCounts[${JSON.stringify(name)}]||0)+1;`);
    found.push(name);
  }
}
const diagnostic=entry+'.diagnostic.mjs';
await writeFile(diagnostic,'const __aotProbeCounts={};\n'+source+'\nexport {__aotProbeCounts};\n');
const measured=await import(pathToFileURL(diagnostic).href),atImport={...measured.__aotProbeCounts};
for(let i=0;i<5;i++)invoke(measured,i);
const duringFiveCalls=Object.fromEntries(found.map(name=>[name,(measured.__aotProbeCounts[name]||0)-(atImport[name]||0)]));
assert.equal(await readFile(entry,'utf8'),original);
const sorted=[...samples].sort((a,b)=>a-b);
const fastSorted=[...emptyHookSamples].sort((a,b)=>a-b);
const median=values=>(values[Math.floor((values.length-1)/2)]+values[Math.floor(values.length/2)])/2;
console.log(JSON.stringify({node:process.version,step_types:count,node_types:count+1,load_ms:loadMs,rounds,
  median_ms:median(sorted),empty_hooks_median_ms:median(fastSorted),
  min_ms:sorted[0],max_ms:sorted.at(-1),samples_ms:samples,empty_hooks_samples_ms:emptyHookSamples,
  diagnostic_functions:found,at_module_import:atImport,during_five_calls:duringFiveCalls,
  outputs_checked:true,original_artifact_modified:false}));
