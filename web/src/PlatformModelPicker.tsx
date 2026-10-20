import {Cpu} from 'lucide-react';
import {Select,SelectTrigger,SelectValue,SelectContent,SelectItem} from '@/components/ui/select';
import {type PlatformModel,yuan} from './billing';

const providers: {name:string;icon:string;match:RegExp}[] = [
 {name:'DeepSeek',icon:'deepseek',match:/deepseek/i},
 {name:'通义千问 · Qwen',icon:'qwen',match:/qwen|qwq|qvq/i},
 {name:'月之暗面 · Kimi',icon:'kimi',match:/kimi|moonshot/i},
 {name:'OpenAI',icon:'openai',match:/openai|gpt|chatgpt|(?:^|\/)o[134](?:-|$)/i},
 {name:'Anthropic · Claude',icon:'claude',match:/claude|anthropic/i},
 {name:'智谱 · GLM',icon:'zhipu',match:/glm|zhipu/i},
 {name:'MiniMax',icon:'minimax',match:/minimax|abab/i},
 {name:'豆包 · Doubao',icon:'doubao',match:/doubao|bytedance|seed(?:-|\d)/i},
 {name:'百度 · 文心',icon:'wenxin',match:/ernie|wenxin|baidu/i},
 {name:'腾讯 · 混元',icon:'hunyuan',match:/hunyuan/i},
 {name:'讯飞 · 星火',icon:'spark',match:/spark|xunfei|iflytek/i},
 {name:'百川智能',icon:'baichuan',match:/baichuan/i},
 {name:'零一万物 · Yi',icon:'yi',match:/(?:^|\/)yi(?:-|\d)/i},
 {name:'阶跃星辰 · Step',icon:'stepfun',match:/stepfun|(?:^|\/)step(?:-|\d)/i},
 {name:'书生 · InternLM',icon:'internlm',match:/internlm/i},
 {name:'Google · Gemini',icon:'gemini',match:/gemini|gemma/i},
 {name:'Meta · Llama',icon:'meta',match:/llama|meta-/i},
 {name:'Mistral',icon:'mistral',match:/mistral|mixtral|codestral|devstral|pixtral/i},
 {name:'xAI · Grok',icon:'grok',match:/grok/i},
];

function ModelIdentity({model}:{model:PlatformModel}){
 const name=model.channel.model;
 const provider=providers.find(p=>p.match.test(name));
 return <span className="platform-model-identity"><span className="model-provider-logo" aria-hidden="true">{provider?<img src={'/model-providers/'+provider.icon+'.svg'} alt="" width="30" height="30"/>:<Cpu size={27}/>}</span><span className="platform-model-name"><strong>{name}</strong><span>{provider?.name||'自定义模型'}</span></span></span>;
}

export default function PlatformModelPicker({role,models,value,onChange}:{role:'text'|'vision';models:PlatformModel[];value:string;onChange:(id:string)=>void}){
 const label=role==='text'?'内容生成模型':'视觉审核模型';
 const selected=models.find(m=>m.id===value);
 const id='platform-model-'+role;
 return <div className="platform-model-field"><span id={id+'-label'} className="platform-model-label">{label}</span><Select value={value} onValueChange={onChange}><SelectTrigger id={id} className="platform-model-trigger" aria-labelledby={id+'-label'} aria-describedby={id+'-price'}><SelectValue placeholder="选择模型">{selected?<ModelIdentity model={selected}/>:undefined}</SelectValue></SelectTrigger><SelectContent className="platform-model-options" sideOffset={6} collisionPadding={12}>{models.map(model=><SelectItem key={model.id} value={model.id} textValue={model.channel.model} className="platform-model-option"><ModelIdentity model={model}/></SelectItem>)}</SelectContent></Select>{selected&&<p className="platform-model-price" id={id+'-price'}><span>每百万 Token</span><span>输入 {yuan(selected.price.input_micro_per_million)} · 输出 {yuan(selected.price.output_micro_per_million)} · 缓存 {yuan(selected.price.cached_micro_per_million)}</span>{selected.price.offpeak_half&&<span>北京时间 22:00–08:00 半价</span>}{selected.price.note&&<span>{selected.price.note}</span>}</p>}</div>;
}
