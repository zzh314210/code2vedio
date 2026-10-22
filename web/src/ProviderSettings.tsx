import ChoiceSelect from './ChoiceSelect';
import type {Channel} from './ModelChannel';
const presets = [
 ['compatible','自定义兼容服务','','chat_completions'],
 ['dashscope','阿里云百炼 / 托管模型','https://dashscope.aliyuncs.com/compatible-mode/v1','chat_completions'],
 ['deepseek','DeepSeek 官方','https://api.deepseek.com/v1','chat_completions'],
 ['moonshot','Kimi / Moonshot 官方','https://api.moonshot.cn/v1','chat_completions'],
 ['openai','OpenAI 官方','https://api.openai.com/v1','responses'],
 ['anthropic','Claude / Anthropic 官方','https://api.anthropic.com/v1','anthropic'],
 ['doubao','豆包 / 火山方舟','https://ark.cn-beijing.volces.com/api/v3','chat_completions'],
 ['zhipu','智谱 GLM','https://open.bigmodel.cn/api/paas/v4','chat_completions'],
 ['minimax','MiniMax','https://api.minimax.io/v1','chat_completions'],
];
export default function ProviderSettings({item,onChange}:{item:Channel;onChange:(v:Partial<Channel>)=>void}) {
 return <div className="settings-grid provider-settings">
  <label className="wide">模型供应商<ChoiceSelect aria-label="模型供应商" value={item.provider||'compatible'} onChange={id=>{
   const p=presets.find(p=>p[0]===id)!;
   onChange({provider:id,stream:id!=='anthropic',protocol:p[3],api_key:'',clear_key:true,...(p[2]?{base_url:p[2]}:{}),thinking_enabled:true,reasoning_effort:'max',extra_body:{}});
  }}>{presets.map(p=><option key={p[0]} value={p[0]}>{p[1]}</option>)}</ChoiceSelect><small>按接口服务商选择；托管的 DeepSeek、Kimi 请选托管服务。地址可修改，切换供应商后需重新填写密钥。</small></label>
  <label className="inline-check"><input type="checkbox" checked={item.thinking_enabled!==false} onChange={e=>onChange({thinking_enabled:e.target.checked})}/>开启深度思考</label>
  <label>思考强度<ChoiceSelect aria-label="思考强度" value={item.reasoning_effort||'max'} disabled={item.thinking_enabled===false} onChange={reasoning_effort=>onChange({reasoning_effort})}><option value="low">轻量 · Low</option><option value="medium">均衡 · Medium</option><option value="high">深入 · High</option><option value="max">最高 · Max</option></ChoiceSelect></label>
  <small className="wide">默认开启最高思考。按供应商注入请求参数；不提供强度调节的模型使用固定思考策略，Claude 旧模型换算为预算，OpenAI 旧型号使用其支持的最高档位。接口拒绝时明确报错，不会静默关闭思考。</small>
 </div>;
}
