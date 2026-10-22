// Local coordination client for Node.js and browser hosts. No lifecycle owner.
export class WorkflowCoordinationError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function portable(value) {
  const visit = item => {
    if(typeof item === "number" && (!Number.isFinite(item) || Number.isInteger(item) && !Number.isSafeInteger(item)))
      throw new TypeError("message numbers must be finite and cross-language safe; encode large integers as strings");
    if(item && typeof item === "object") {
      if(!Array.isArray(item) && Object.getPrototypeOf(item)!==Object.prototype && Object.getPrototypeOf(item)!==null)
        throw new TypeError("message values must be ordinary JSON");
      for(const child of Object.values(item))visit(child);
    } else if(!["string","number","boolean"].includes(typeof item) && item!==null)
      throw new TypeError("message values must be ordinary JSON");
  };
  visit(value);
  return JSON.parse(JSON.stringify(value));
}

export class WorkflowClient {
  static async open(url, {id=null, workflow=null, onStop=null}={}) {
    const client = new WorkflowClient(url);
    const registered = await client.request("register", {id, workflow, stop_supported:Boolean(onStop)});
    client.id=registered.id;client.inputs=registered.inputs;client.entry=registered.entry;client.workflow=registered.workflow;
    if(onStop)client.watching=client.watch(onStop);
    return client;
  }
  constructor(url) {
    this.url=url.replace(/\/$/,"");this.pending=Promise.resolve();this.errors=[];
    this.closed=false;this.controller=new AbortController();
  }
  async request(operation, value, signal) {
    const response=await fetch(this.url+"/"+operation,{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(portable(value)),signal});
    const result=await response.json();
    if(result.error)throw new WorkflowCoordinationError(result.error.code,result.error.message);
    return result.value;
  }
  async watch(stop) {
    try {
      while(!this.closed) {
        const state=await this.request("control",{id:this.id},this.controller.signal);
        if(state.stop){await stop();return;}
        if(state.ended)return;
      }
    } catch(error) { if(!this.closed)this.errors.push(error); }
  }
  send(id, port, payload) {
    if(this.closed||this.finishing)throw new WorkflowCoordinationError("VF_INSTANCE_ENDED",this.id);
    const value=portable({id,sender:this.id,port,payload});
    this.pending=this.pending.then(()=>this.request("send",value)).catch(error=>{this.errors.push(error);});
  }
  async flush() {await this.pending;if(this.errors.length)throw this.errors[0];}
  async poll(operation, id, {port,timeout,signal}={}) {
    const deadline=timeout==null?Infinity:Date.now()+timeout*1000;
    while(true) {
      signal?.throwIfAborted();
      if(this.closed)throw new WorkflowCoordinationError("VF_INSTANCE_ENDED",this.id);
      if(Date.now()>=deadline)throw new WorkflowCoordinationError("VF_WAIT_TIMEOUT",id);
      const value={id};if(port!==undefined)value.port=port;
      const result=await this.request(operation,value,signal);
      if(!result.pending)return result;
    }
  }
  async call(workflow, {launch,inputs={},timeout,signal}={}) {
    workflow={...workflow,root:workflow?.root||this.workflow?.root||""};
    const launched=await this.request("call",{sender:this.id,workflow,launch,inputs},signal);
    return this.poll("ready",launched.id,{timeout,signal});
  }
  wait(id, options={}) {return this.poll("wait",id,options);}
  receive(port="default", options={}) {return this.poll("receive",this.id,{...options,port});}
  async kill(id, options={}) {await this.request("kill",{id,...(options.workflow?{workflow:{...options.workflow,root:options.workflow.root||this.workflow?.root||""}}:{})},options.signal);return this.wait(id,options);}
  operations() {
    return {
      self:()=>({id:this.id}),
      call:(request,context={})=>this.call(request.workflow,{...request,signal:context.signal}),
      wait:(request,context={})=>this.wait(request.id,{...request,signal:context.signal}),
      send:request=>{this.send(request.id,request.port||"default",request.payload);return null;},
      receive:(request,context={})=>this.receive(request.port||"default",{...request,signal:context.signal}),
      kill:(request,context={})=>this.kill(request.id,{...request,signal:context.signal}),
    };
  }
  finish(options={}) {
    if(!this.finishing)this.finishing=this.complete(options);
    return this.finishing;
  }
  async complete({state="succeeded",outputs=null,error=null}={}) {
    if(this.closed)return;
    try {
      let deliveryError;
      try {await this.flush();}catch(failure){deliveryError=failure;state="failed";error={code:failure.code||"VF_DELIVERY_FAILED",message:String(failure)};}
      let payload={id:this.id,state,outputs,error};
      try {payload=portable(payload);}
      catch(failure){deliveryError ||= failure;payload={id:this.id,state:"failed",outputs:null,
        error:{code:"VF_RESULT_NOT_JSON",message:String(failure)}};}
      const result=await this.request("complete",payload);
      if(deliveryError)throw deliveryError;
      return result;
    } finally {this.closed=true;this.controller.abort();}
  }
}
