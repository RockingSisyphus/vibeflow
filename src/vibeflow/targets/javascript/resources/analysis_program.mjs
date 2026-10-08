import {mkdtemp,readFile,rm,writeFile} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export class AnalysisSession {
  constructor(){this.programs=new Map();this.functions=new Map();this.callGraphs=new Map();this.owned=[];}
  metric(store,sourceFile,extra,create){
    const key=JSON.stringify([path.resolve(sourceFile.fileName),sourceFile.getFullText(),extra]);
    if(!store.has(key))store.set(key,create());
    return store.get(key);
  }
  async dispose(){
    const errors=[];
    for(const release of this.owned.splice(0).reverse())try{await release();}catch(error){errors.push(error);}
    this.programs.clear();this.functions.clear();this.callGraphs.clear();
    if(errors.length)throw errors[0];
  }
}

async function textAt(file,snapshots){
  if(snapshots.has(file))return snapshots.get(file);
  try{return await readFile(file,"utf8");}catch{return null;}
}

async function unchanged(entry,snapshots){
  for(const [file,text] of entry.texts){if(await textAt(file,snapshots)!==text)return false;}
  return true;
}

export async function analysisProgram(ts,request,files,jsonCompilerOptions,session){
  const snapshots=new Map((request.sourceSnapshots||[]).map(source=>[path.resolve(source.path),source.text]));
  const key=JSON.stringify([path.resolve(request.packageRoot),String(ts.version||""),!!ts.__native,
    [...files].sort(),jsonCompilerOptions,request.workflowEntry?path.dirname(request.workflowEntry):""]);
  const cached=session?.programs.get(key);
  if(cached&&await unchanged(cached,snapshots))return {...cached,dispose:async()=>{}};
  let program,checker,project=null,sourceFiles,snapshot,api,temporaryConfigRoot;
  let release=async()=>{};
  if(ts.__native){
    const configDirectory=request.workflowEntry?path.dirname(request.workflowEntry):
      (temporaryConfigRoot=await mkdtemp(path.join(os.tmpdir(),"vibeflow-audit-ts-")));
    const configPath=path.join(configDirectory,request.contractCheckFiles?.length?"tsconfig.vibeflow.json":"tsconfig.vibeflow-closure.json");
    release=async()=>{try{snapshot?.dispose();}finally{try{api?.close();}finally{if(temporaryConfigRoot)await rm(temporaryConfigRoot,{recursive:true,force:true});}}};
    try{
      await writeFile(configPath,JSON.stringify({compilerOptions:jsonCompilerOptions,files}),"utf8");
      api=new ts.API({cwd:path.resolve(request.packageRoot),fs:{
        readFile:name=>snapshots.get(path.resolve(name)),
        fileExists:name=>snapshots.has(path.resolve(name))?true:undefined}});
      snapshot=api.updateSnapshot({openProjects:[configPath]});
      project=snapshot.getProject(configPath)||snapshot.getProjects()[0];
      if(!project){const error=new Error("TypeScript did not create a project for AOT validation");error.code="VF_TYPESCRIPT";throw error;}
      program=project.program;checker=project.checker;
      sourceFiles=program.getSourceFileNames().map(file=>program.getSourceFile(file)).filter(Boolean);
    }catch(error){await release();throw error;}
  }else{
    const options={...jsonCompilerOptions,target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,
      moduleResolution:ts.ModuleResolutionKind.Bundler,
      lib:request.target==="node"?["lib.es2022.d.ts"]:["lib.es2022.d.ts","lib.dom.d.ts","lib.dom.iterable.d.ts"]};
    const host=ts.createCompilerHost(options),read=host.readFile.bind(host);
    host.readFile=name=>snapshots.get(path.resolve(name))??read(name);
    program=ts.createProgram({rootNames:files,options,host});checker=program.getTypeChecker();sourceFiles=program.getSourceFiles();
  }
  // Local closure text participates in reuse. Installed backend/library code is
  // fixed for this command; source snapshots remain authoritative when present.
  const texts=new Map();
  for(const file of sourceFiles){const absolute=path.resolve(file.fileName);if(!absolute.includes(`${path.sep}node_modules${path.sep}`))texts.set(absolute,file.getFullText());}
  for(const file of files)if(!texts.has(file))texts.set(file,await textAt(file,snapshots));
  const entry={program,checker,project,sourceFiles,texts};
  if(session){session.programs.set(key,entry);session.owned.push(release);return {...entry,dispose:async()=>{}};}
  return {...entry,dispose:release};
}
