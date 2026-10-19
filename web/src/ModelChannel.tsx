import {useEffect, useRef, useState} from 'react';
import {KeyRound, LoaderCircle, RefreshCw, Search} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {request, jsonRequest} from './services';

export type Channel = {
 max_tokens?:number; stream?:boolean; extra_body?:Record<string,boolean>;
 base_url:string; model:string; api_key?:string; protocol?:string;
 fallback_models?:string[]; key_configured?:boolean; clear_key?:boolean;
 voice?:string; provider?:string;
};
type Role = 'text'|'vision'|'tts';

export default function ModelChannel({role,title,description,item,onChange}:{
 role:Role; title:string; description:string; item:Channel;
 onChange:(values:Partial<Channel>)=>void;
}) {
 const [models,setModels]=useState<string[]|null>(null);
 const [query,setQuery]=useState('');
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const pending=useRef<AbortController|null>(null);
 useEffect(()=>{
  pending.current?.abort();setModels(null);setQuery('');setError('');setLoading(false);
  return ()=>pending.current?.abort();
 },[item.base_url,item.api_key,item.clear_key,item.key_configured]);
 const load=async()=>{
  pending.current?.abort();const controller=new AbortController();pending.current=controller;
  setLoading(true);setError('');setModels(null);
  try {
   const result=await request<{models:string[]}>('/api/config/models',{
    ...jsonRequest('POST',{role,base_url:item.base_url,api_key:item.api_key||'',clear_key:Boolean(item.clear_key)}),
    signal:controller.signal,
   });
   if(!controller.signal.aborted)setModels(result.models);
  } catch(e) {if(!controller.signal.aborted)setError((e as Error).message)}
  finally {if(!controller.signal.aborted)setLoading(false)}
 };
 const filtered=models?.filter(model=>model.toLowerCase().includes(query.trim().toLowerCase()))||[];
 const keyLabel=role==='text'?'内容生成密钥':role==='vision'?'视觉审核密钥':'配音服务密钥';
 return <fieldset className="settings-card model-channel">
  <legend><span className="section-icon"><KeyRound size={17}/></span>{title}<span className={'pill '+(item.key_configured&&!item.clear_key?'success':'warning')}>{item.clear_key?'待移除':item.api_key?'密钥待保存':item.key_configured?'密钥已保存':'待配置'}</span></legend>
  <p>{description}</p>
  <div className="model-setup-steps" aria-label="配置步骤"><span>1 填写地址</span><span>2 填写密钥</span><span>3 选择模型</span></div>
  <div className="settings-grid">
   <label className="wide">服务地址<Input name={role+'-url'} type="url" autoComplete="off" value={item.base_url} onChange={e=>onChange({base_url:e.target.value})} placeholder="https://服务商域名/v1"/><small>填写服务商提供的接口地址。更换地址后，请重新填写该服务的密钥。</small></label>
   <label className="wide">{keyLabel}<Input name={role+'_api_key'} type="password" autoComplete="off" value={item.api_key||''} onChange={e=>onChange({api_key:e.target.value,clear_key:false})} placeholder={item.key_configured?'已加密保存；留空保留原密钥':'粘贴此服务的访问密钥'}/><small>仅用于当前服务，不会显示给其他用户。</small></label>
   <div className="wide model-discovery">
    <div className="model-discovery-heading"><div><strong>选择模型</strong><small>可以从服务商获取列表，也可以直接填写。</small></div><Button type="button" variant="outline" disabled={loading||!item.base_url.trim()||item.clear_key||(!item.api_key?.trim()&&!item.key_configured)} onClick={()=>void load()} aria-label={'获取'+title+'模型列表'}>{loading?<LoaderCircle className="spin" size={16}/>:<RefreshCw size={16}/>} {loading?'正在获取…':'获取模型列表'}</Button></div>
    {error&&<p className="editor-error" role="alert">{error}</p>}
    {models!==null&&<div className="model-list-panel">
     <p role="status">{models.length?`已获取 ${models.length} 个模型，请选择适合此用途的模型。`:'此服务暂未返回可用模型，可以手动填写模型名称。'}</p>
     {models.length>0&&<><label className="model-search"><Search size={16}/><Input name={role+'-model-search'} aria-label={'搜索'+title+'模型'} type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索模型名称"/></label><label>可用模型<select aria-label={title+'可用模型'} value="" onChange={e=>{if(e.target.value){onChange({model:e.target.value});setQuery('')}}}><option value="">{filtered.length?'请选择一个模型':'没有匹配的模型'}</option>{filtered.map(model=><option key={model} value={model}>{model}</option>)}</select></label></>}
    </div>}
   </div>
   <label className="wide">模型名称<Input name={role+'-model'} autoComplete="off" value={item.model} onChange={e=>onChange({model:e.target.value})} placeholder="选择上方模型，或手动输入模型名称"/><small>{role==='vision'?'请选择支持图片输入的模型；列表中的名称保留服务商原名。':'使用服务商提供的模型名称，保存后用于此项服务。'}</small></label>
   {role==='tts'&&<label className="wide">音色名称<Input name="tts-voice" value={item.voice||''} onChange={e=>onChange({voice:e.target.value})} placeholder="填写服务商支持的音色名称"/></label>}
  </div>
  {role!=='tts'&&<details className="model-advanced"><summary>高级设置 <span>一般保持默认即可</span></summary><div className="settings-grid"><label>接口类型<select value={item.protocol} onChange={e=>onChange({protocol:e.target.value})}><option value="chat_completions">对话接口（常见）</option><option value="responses">响应接口</option></select></label><label>最大输出长度<Input type="number" name={role+'-max-tokens'} min={256} max={100000} value={item.max_tokens||12000} onChange={e=>onChange({max_tokens:Number(e.target.value)})}/><small>控制单次生成的内容上限，一般保持默认即可。</small></label><label className="wide">备用模型 <span className="optional">可选</span><Input name={role+'-fallbacks'} autoComplete="off" value={(item.fallback_models||[]).join(',')} onChange={e=>onChange({fallback_models:e.target.value?e.target.value.split(','):[]})} placeholder="多个模型名称用英文逗号分隔"/><small>主模型不可用时按顺序尝试，使用同一服务地址和密钥。</small></label></div></details>}
  {item.key_configured&&<label className="checkbox-label model-remove"><input type="checkbox" checked={Boolean(item.clear_key)} onChange={e=>onChange({clear_key:e.target.checked,api_key:''})}/>保存时移除此密钥</label>}
 </fieldset>;
}
