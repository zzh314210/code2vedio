import {useEffect,useState} from 'react';
import {Clock3,ListOrdered,Trash2} from 'lucide-react';
import {request} from './services';
import './queue.css';

export type QueueState={state:string;position:number;ahead:number;waiting:number;wait_minutes:[number,number]|null;remaining_minutes:[number,number];waiting_for:string;active_stage?:string;concurrency:number};
const stageNames:Record<string,string>={outline:'整理大纲',storyboard:'编排分镜',audio:'合成配音',assets:'整理素材',code:'制作动画',render:'渲染画面',review:'检查画面',compose:'合成成片',analyze:'分析素材',planning:'编排剪辑',transcribe:'识别语音',prepare:'准备制作'};
export function QueueStatus({queue,cancelPath}:{queue?:QueueState;cancelPath?:string}){
 const[busy,setBusy]=useState(false),[error,setError]=useState(''),[cancelled,setCancelled]=useState(false);
 if(!queue||queue.state!=='queued')return null;
 const cancel=async()=>{setBusy(true);setError('');try{await request(cancelPath!,{method:'POST'});setCancelled(true);window.dispatchEvent(new Event('frame-queue-changed'))}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <div className="queue-status" role="status"><div><ListOrdered size={16}/><strong>{cancelled?'已取消排队':queue.waiting_for==='memory'?'等待可用资源':queue.ahead?`前面还有 ${queue.ahead} 条任务`:'即将轮到你'}</strong><span>按用户轮流制作</span></div>{!cancelled&&<p>{queue.wait_minutes?queue.ahead?`预计等待 ${queue.wait_minutes[0]}–${queue.wait_minutes[1]} 分钟。`:'资源就绪后自动开始。':'内存恢复后自动继续，暂无法准确估算等待时间。'}{queue.active_stage&&`当前制作：${stageNames[queue.active_stage]||'处理素材'}。`}</p>}{cancelPath&&!cancelled&&<button onClick={()=>void cancel()} disabled={busy}><Trash2 size={12}/>{busy?'正在取消…':'取消排队'}</button>}{error&&<p className="queue-error">{error}</p>}</div>
}

export function RetentionBadge({expiresAt,permanent,status}:{expiresAt?:number;permanent?:boolean;status?:string}){
 const[now,setNow]=useState(Date.now()/1000);useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()/1000),60000);return()=>clearInterval(timer)},[]);
 if(permanent)return <span className="retention-badge permanent">永久样片</span>;
 if(status==='expired')return <span className="retention-badge">已超过 24 小时，文件已自动清理</span>;
 if(!expiresAt||['queued','running','revising','uploading','analyzing','rendering'].includes(status||''))return null;
 const hours=Math.max(0,Math.ceil((expiresAt-now)/3600));
 return <span className={'retention-badge'+(hours<=3?' urgent':'')} title={'保存至 '+new Date(expiresAt*1000).toLocaleString('zh-CN')}><Clock3 size={12}/>{hours?`约 ${hours} 小时后自动清理，请及时下载`:'即将自动清理，请及时下载'}</span>
}
