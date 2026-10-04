import {defineHostExtension} from "@vibeflow/plugin";
import {library} from "./math.ts";
import {createSession} from "./host_support.ts";
import type {SessionValue} from "./types.d.ts";
export const host=defineHostExtension({id:"demo.host",targets:["node","browser"],provides:["demo.session"],base_libs:["demo.math"],implementation_files:["host_support.ts","types.d.ts"],rulesets:["vibeflow.host_extension"],presentation:{fill:"#ffd9bb",shape:"hex",icon:"H"},createHost(){const session=createSession();return {capabilities:{"demo.session":{next(value:SessionValue){return session.next(library.implementation(value));}}},start(){session.start();},stop(){session.stop();}};}});
