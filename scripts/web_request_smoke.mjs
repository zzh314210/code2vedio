// Exercise request behavior independently of React: reads may recover; mutations must not replay.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from '../web/node_modules/typescript/lib/typescript.js';
const source=readFileSync(new URL('../web/src/services.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {request}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
globalThis.window=new EventTarget();
let calls=0;
globalThis.fetch=async()=>{if(++calls===1)throw new TypeError('Load failed');return Response.json({ok:true})};
assert.deepEqual(await request('/api/jobs'),{ok:true});assert.equal(calls,2);
calls=0;
globalThis.fetch=async()=>++calls<3?new Response('upstream unavailable',{status:503}):Response.json({ok:true});
assert.deepEqual(await request('/api/usage'),{ok:true});assert.equal(calls,3);
for(const method of ['POST','PUT','PATCH','DELETE']){
 calls=0;globalThis.fetch=async(_url,options)=>{calls++;assert.equal(options.headers.get('X-Frame-Request'),'1');throw new TypeError('Load failed')};
 await assert.rejects(request('/api/jobs',{method}),/操作结果尚未确认/);assert.equal(calls,1);
}
calls=0;globalThis.fetch=async()=>{calls++;throw new TypeError('Failed to fetch')};
await assert.rejects(request('/api/jobs'),/连接暂时中断/);assert.equal(calls,3);
let expired=0,credit=0;
window.addEventListener('frame-session-expired',()=>expired++);window.addEventListener('frame-balance-required',()=>credit++);
for(const [status,url] of [[401,'/api/jobs'],[401,'/api/auth/me'],[401,'/api/auth/login'],[402,'/api/jobs']]){
 calls=0;globalThis.fetch=async()=>{calls++;return new Response('error',{status})};
 await assert.rejects(request(url),error=>error.status===status);assert.equal(calls,1);
}
assert.equal(expired,1);assert.equal(credit,1);
const cancelled=new AbortController();cancelled.abort();calls=0;
globalThis.fetch=async()=>{calls++;return Response.json({})};
await assert.rejects(request('/api/jobs',{signal:cancelled.signal}),{name:'AbortError'});assert.equal(calls,0);
const active=new AbortController();calls=0;
globalThis.fetch=async()=>{calls++;setTimeout(()=>active.abort(),5);throw new TypeError('Load failed')};
await assert.rejects(request('/api/jobs',{signal:active.signal}),{name:'AbortError'});assert.equal(calls,1);
globalThis.fetch=async()=>new Response(null,{status:204});
assert.equal(await request('/api/auth/logout',{method:'POST'}),undefined);
console.log('PASS: read recovery, bounded retries, mutations never replay, cancellation, session/payment events, empty success response.');
