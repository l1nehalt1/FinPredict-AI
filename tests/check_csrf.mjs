import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

const source=fs.readFileSync('lib/api.ts','utf8').replace("import {tr} from './i18n';",'const tr=(text:string)=>text;');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const rejected={error:'Обновите страницу и повторите действие'};
async function run(responses,action){
 const calls=[];
 globalThis.fetch=async(path,options)=>{
  calls.push({path,...options});
  const reply=responses.shift();assert.ok(reply,'Unexpected extra request');
  if(reply instanceof Error)throw reply;
  return new Response(JSON.stringify(reply.body),{status:reply.status});
 };
 const exports={};new Function('exports',compiled)(exports);
 await action(exports.api,calls);
 assert.equal(responses.length,0);
}
for(const path of ['/api/auth/login','/api/auth/register']){
 await run([{status:403,body:rejected},{status:200,body:{csrfToken:'fresh',user:null}},{status:200,body:{user:{role:'admin'},csrfToken:'logged-in'}}],async(api,calls)=>{
  const body=JSON.stringify({email:'admin@example.test',password:'test-only'});
  const result=await api(path,{method:'POST',body,headers:new Headers({'X-CSRF-Token':'stale','X-Test':'keep'})});
  assert.equal(result.user.role,'admin');
  assert.deepEqual(calls.map(c=>c.path),[path,'/api/auth/me',path]);
  assert.equal(calls[2].body,body);
  assert.equal(calls[2].headers.get('X-CSRF-Token'),'fresh');
  assert.equal(calls[2].headers.get('X-Test'),'keep');
  assert.ok(calls.every(c=>c.credentials==='same-origin'));
 });
}
await run([{status:403,body:rejected},{status:200,body:{csrfToken:'fresh'}},{status:403,body:rejected}],async(api,calls)=>{
 await assert.rejects(api('/api/auth/login',{method:'POST',body:'{}'}),/Обновите страницу/);
 assert.equal(calls.length,3);
});
for(const [path,status,error] of [['/api/auth/login',401,'Неверный email или пароль'],['/api/auth/login',403,'Доступ запрещён'],['/api/transactions',403,rejected.error]]){
 await run([{status,body:{error}}],async(api,calls)=>{await assert.rejects(api(path,{method:'POST',body:'{}'}));assert.equal(calls.length,1);});
}
await run([{status:403,body:rejected},{status:500,body:{error:'Refresh failed'}}],async(api,calls)=>{
 await assert.rejects(api('/api/auth/login',{method:'POST',body:'{}'}),/Refresh failed/);assert.equal(calls.length,2);
});
await run([new DOMException('Cancelled','AbortError')],async(api,calls)=>{
 await assert.rejects(api('/api/auth/login',{method:'POST',body:'{}'}),e=>e.name==='AbortError');assert.equal(calls.length,1);
});
console.log('CSRF login/registration recovery, retry limit and mutation safety checks passed');
