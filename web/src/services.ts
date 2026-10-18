export async function request<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch(url,options);const value=await response.json();
 if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'请检查输入后重试。');return value;
}
export const jsonRequest=(method:string,value:unknown):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
