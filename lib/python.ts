// A server-only MicroPython WebAssembly interpreter executes backend/finance.py.
import {loadMicroPython} from './python_runtime/micropython.mjs';
import wasm from './python_runtime/micropython.wasm';
import source from '../backend/finance.py?raw';
let runtime:Promise<any>|undefined;
export async function calculate<T>(payload:unknown):Promise<T>{
 runtime??=loadMicroPython({heapsize:8*1024*1024,pystack:64*1024,instantiateWasm:(imports:any,receive:any)=>{const instance=new WebAssembly.Instance(wasm,imports);receive(instance);return instance.exports;}}).then((mp:any)=>{mp.runPython(source);return mp;}).catch((e:any)=>{runtime=undefined;throw e;});
 const mp=await runtime;
 // No awaits between writing the request and reading its result, so requests
 // cannot interleave in the isolate's shared interpreter.
 mp.runPython(`_result = run_json(${JSON.stringify(JSON.stringify(payload))})`);
 const output=mp.pyimport('__main__')._result;
 mp.runPython('import gc; gc.collect()');
 return JSON.parse(output);
}
