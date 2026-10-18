let started=0,release:()=>void;
let barrier=new Promise<void>(resolve=>release=resolve);
export function terminal(){return {};}
async function worker(inputs:any,params:any,context:any){
 const index=params.index;context.trace('worker_started',{index});
 try {
  const phase=barrier;
  if(++started===12){release();started=0;barrier=new Promise<void>(resolve=>release=resolve);}
  await phase;
  await new Promise(resolve=>setTimeout(resolve,12-index));
  return index as number;
 } finally {await new Promise(resolve=>setTimeout(resolve,5));context.trace('cleanup_finished',{index});}
}
export function collect(inputs:any){return {report:inputs.receipt.map((item:any)=>item.value)};}

export async function worker0(inputs:any,params:any,context:any){return {receipt0:await worker(inputs,params,context)};}
export async function worker1(inputs:any,params:any,context:any){return {receipt1:await worker(inputs,params,context)};}
export async function worker2(inputs:any,params:any,context:any){return {receipt2:await worker(inputs,params,context)};}
export async function worker3(inputs:any,params:any,context:any){return {receipt3:await worker(inputs,params,context)};}
export async function worker4(inputs:any,params:any,context:any){return {receipt4:await worker(inputs,params,context)};}
export async function worker5(inputs:any,params:any,context:any){return {receipt5:await worker(inputs,params,context)};}
export async function worker6(inputs:any,params:any,context:any){return {receipt6:await worker(inputs,params,context)};}
export async function worker7(inputs:any,params:any,context:any){return {receipt7:await worker(inputs,params,context)};}
export async function worker8(inputs:any,params:any,context:any){return {receipt8:await worker(inputs,params,context)};}
export async function worker9(inputs:any,params:any,context:any){return {receipt9:await worker(inputs,params,context)};}
export async function worker10(inputs:any,params:any,context:any){return {receipt10:await worker(inputs,params,context)};}
export async function worker11(inputs:any,params:any,context:any){return {receipt11:await worker(inputs,params,context)};}
