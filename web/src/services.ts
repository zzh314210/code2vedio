export async function request<T>(url:string,options?:RequestInit):Promise<T>{
 const headers=new Headers(options?.headers);
 if(options?.method && !['GET','HEAD'].includes(options.method.toUpperCase()))headers.set('X-Frame-Request','1');
 const response=await fetch(url,{...options,headers,credentials:'same-origin'});
 let value;try{value=await response.json()}catch{throw Error('服务暂时不可用，请稍后重试。')}
 if(!response.ok){if(response.status===402)window.dispatchEvent(new Event('frame-balance-required'));if(response.status===401&&!['/api/auth/login','/api/auth/me'].includes(url))window.dispatchEvent(new Event('frame-session-expired'));throw Error(typeof value.detail==='string'?value.detail:'请检查输入后重试。')}
 return value;
}
export const jsonRequest=(method:string,value:unknown):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export type User={id:string;username:string;display_name:string;role:'user'|'admin';active:boolean;balance_cents:number;created_at:number};
export const money=(cents:number)=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(cents/100);
export const date=(seconds:number)=>new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(seconds*1000));
