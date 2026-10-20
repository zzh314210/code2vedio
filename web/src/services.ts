class APIError extends Error {
 constructor(message:string,readonly status:number){super(message)}
}
class ConnectionError extends Error {}

function delay(ms:number,signal?:AbortSignal|null){
 return new Promise<void>((resolve,reject)=>{
  const done=()=>{signal?.removeEventListener('abort',abort);resolve()};
  const timer=setTimeout(done,ms);
  const abort=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);reject(new DOMException('Request cancelled','AbortError'))};
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
 });
}

export async function request<T>(url:string,options?:RequestInit & {timeoutMs?:number}):Promise<T>{
 const method=(options?.method||'GET').toUpperCase();
 const readOnly=method==='GET'||method==='HEAD';
 const headers=new Headers(options?.headers);
 if(!readOnly)headers.set('X-Frame-Request','1');
 for(let attempt=0;attempt<3;attempt++){
  const controller=new AbortController();
  const cancelled=()=>controller.abort();
  if(options?.signal?.aborted)throw new DOMException('Request cancelled','AbortError');
  options?.signal?.addEventListener('abort',cancelled,{once:true});
  const timer=readOnly?setTimeout(()=>controller.abort(),options?.timeoutMs||15000):undefined;
  try{
   let response:Response,value;
   try{
    const {timeoutMs:_,...fetchOptions}=options||{};
    response=await fetch(url,{...fetchOptions,headers,signal:controller.signal,credentials:'same-origin'});
    try{value=response.status===204?undefined:await response.json()}catch(error){
     if(response.ok)throw error;
     value=null;
    }
   }catch(error){
    if(options?.signal?.aborted)throw new DOMException('Request cancelled','AbortError');
    if(error instanceof APIError)throw error;
    throw new ConnectionError(readOnly?'连接暂时中断，请检查网络后重试。':'连接中断，操作结果尚未确认，请先刷新查看，避免重复提交。');
   }
   if(!response.ok){
    if(response.status===402)window.dispatchEvent(new Event('frame-balance-required'));
    if(response.status===401&&!['/api/auth/login','/api/auth/me'].includes(url))window.dispatchEvent(new Event('frame-session-expired'));
    throw new APIError(typeof value?.detail==='string'?value.detail:response.status>=500?'服务暂时不可用，请稍后重试。':'请检查输入后重试。',response.status);
   }
   return value as T;
  }catch(error){
   const retry=error instanceof ConnectionError||(error instanceof APIError&&[502,503,504].includes(error.status));
   if(!readOnly||attempt===2||!retry||options?.signal?.aborted)throw error;
  }finally{
   clearTimeout(timer);options?.signal?.removeEventListener('abort',cancelled);
  }
  await delay(attempt===0?350:900,options?.signal);
 }
 throw new Error('暂时无法读取数据，请重试。');
}
export const jsonRequest=(method:string,value:unknown):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export type User={id:string;username:string;display_name:string;role:'user'|'admin';active:boolean;balance_cents:number;created_at:number};
export const money=(cents:number)=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(cents/100);
export const date=(seconds:number)=>new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(seconds*1000));
