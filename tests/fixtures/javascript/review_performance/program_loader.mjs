export async function load(url,context,nextLoad){
  const result=await nextLoad(url,context);
  if(url.endsWith('/analysis_program.mjs')&&process.env.VIBEFLOW_PROGRAM_PROBE){
    const source=String(result.source);
    const marker='let program,checker';
    if(!source.includes(marker))throw new Error('Program probe marker missing');
    result.source='import {appendFileSync as observeProgramBuild} from "node:fs";\n'+source.replace(marker,
      'observeProgramBuild(process.env.VIBEFLOW_PROGRAM_PROBE,JSON.stringify({files:files.length})+"\\n");'+marker);
  }
  return result;
}
