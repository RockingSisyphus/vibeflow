export async function run(inputs:any,params:any,context:any){
  const response = await (inputs as any)["app.session"].value.storage.read({key:inputs["addition.key"].value},{signal:context.signal});
  return {a:response.value,b_next:inputs["addition.b"].value};
}
