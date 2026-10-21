export async function run(inputs:any,params:any,context:any){
  const response = await context.capabilities["addition.storage"].read({key:inputs["addition.key"].value});
  return {a:response.value,b_next:inputs["addition.b"].value};
}
