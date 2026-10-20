import {useEffect,useState} from 'react';
import {ArrowDown,ArrowUp,ArrowUpToLine,Clock3,ListOrdered,LoaderCircle,RefreshCw,Trash2} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {request,jsonRequest,type User} from './services';
import './queue.css';
type Task={seq:number;identity:string;owner:string;title:string;kind:string;state:string;stage:string;created:number;estimate_minutes:[number,number]};
type Queue={running:Task[];waiting:Task[];version:string;manual_order:boolean;other_environment_running:boolean;concurrency:number;user_waiting_limit:number;resources:{memory_mb:number;memory_limit_mb:number;swap_mb:number;swap_limit_mb:number;available_mb:number;cpu_limit:number;ready:boolean};audit:{actor:string;action:string;created:number}[]};
export default function AdminQueue({users}:{users:User[]}){
 const[data,setData]=useState<Queue|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const load=async()=>{try{setData(await request<Queue>('/api/admin/queue'));setError('')}catch(e){setError((e as Error).message)}};
 useEffect(()=>{void load();const timer=setInterval(()=>{if(!document.hidden&&!busy)void load()},5000);return()=>clearInterval(timer)},[busy]);
 const order=async(ids:number[])=>{if(!data)return;setBusy(true);setError('');try{setData(await request<Queue>('/api/admin/queue/order',jsonRequest('PUT',{order:ids,version:data.version})));setNotice(ids.length?'队列顺序已调整。':'已恢复按用户轮流制作。')}catch(e){setError((e as Error).message);void load()}finally{setBusy(false)}};
 const move=(index:number,destination:number)=>{if(!data)return;const next=data.waiting.map(t=>t.seq);const[value]=next.splice(index,1);next.splice(destination,0,value);void order(next)};
 const cancel=async(task:Task)=>{if(!window.confirm('取消排队任务“'+task.title+'”？尚未开始的模型调用不会扣费。'))return;setBusy(true);try{await request('/api/admin/queue/'+task.seq,{method:'DELETE'});await load();setNotice('任务已移出队列，用户可以看到取消状态。')}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const owner=(id:string)=>users.find(u=>u.id===id)?.username||id.slice(0,8);
 const stage=(value:string)=>({outline:'整理大纲',storyboard:'编排分镜',audio:'合成配音',assets:'整理素材',code:'制作动画',render:'渲染画面',review:'检查画面',compose:'合成成片',analyze:'分析素材',planning:'编排剪辑',prepare:'准备制作'}[value]||'处理素材');
 const kind=(value:string)=>value==='edit'?'AI 剪辑':value==='advice'?'AI 审核':'视频创作';
 return <section className="settings-card queue-admin"><div className="billing-section-title"><div><h2><ListOrdered size={20}/>制作队列</h2><p>一次制作一条，每个用户每轮一条。人工确认期间让出制作位置。</p></div><Button variant="outline" onClick={()=>void load()} disabled={busy}><RefreshCw size={15}/>刷新</Button></div>{error&&<p className="editor-error" role="alert">{error}</p>}{notice&&<p className="success-notice" role="status">{notice}</p>}{data?<>
  <div className="queue-metrics"><div><small>正在制作 / 等待</small><strong>{data.running.length} <span>/ {data.waiting.length}</span></strong></div><div><small>项目内存</small><strong>{data.resources.memory_mb} <span>/ {data.resources.memory_limit_mb} MB</span></strong></div><div><small>Swap 使用</small><strong>{data.resources.swap_mb} <span>/ {data.resources.swap_limit_mb} MB</span></strong></div><div><small>CPU 总上限</small><strong>{data.resources.cpu_limit}<span> 核</span></strong></div></div>
  {data.running.map(task=><article className="queue-active" key={task.seq}><LoaderCircle size={20} className="spin"/><div><strong>{task.title}</strong><p>{owner(task.owner)} · {kind(task.kind)} · 阶段：{stage(task.stage)} · 预计还需 {task.estimate_minutes.join('–')} 分钟</p></div><span>制作中</span></article>)}
  {!data.resources.ready&&!data.running.length&&<p className="queue-resource-note">系统正在等待内存释放。任务已保存，资源恢复后自动继续。</p>}
  {data.other_environment_running&&!data.running.length&&<p className="queue-resource-note">另一个工作环境正在制作，本站队列会自动接续。</p>}
  <div className="queue-waiting-heading"><h3>待处理 <span>{data.waiting.length}</span></h3><Button variant="outline" disabled={busy||!data.manual_order} onClick={()=>void order([])}>恢复公平排序</Button></div>
  {!data.waiting.length?<div className="queue-empty"><Clock3 size={23}/><strong>队列很空，灵感可以出发了。</strong><p>每个用户最多保留 {data.user_waiting_limit} 条待处理任务。</p></div>:<ol className="admin-queue-list">{data.waiting.map((task,index)=><li key={task.seq}><span className="queue-position">{index+1}</span><div><strong>{task.title}</strong><p>{owner(task.owner)} · {kind(task.kind)} · 本任务预计 {task.estimate_minutes.join('–')} 分钟</p></div><div className="queue-row-actions"><button title="移到最前" aria-label={'优先处理 '+task.title} disabled={busy||!index} onClick={()=>move(index,0)}><ArrowUpToLine size={15}/></button><button aria-label={'上移 '+task.title} disabled={busy||!index} onClick={()=>move(index,index-1)}><ArrowUp size={15}/></button><button aria-label={'下移 '+task.title} disabled={busy||index===data.waiting.length-1} onClick={()=>move(index,index+1)}><ArrowDown size={15}/></button><button aria-label={'取消 '+task.title} disabled={busy} onClick={()=>void cancel(task)}><Trash2 size={15}/></button></div></li>)}</ol>}
  <p className="queue-admin-note">调序与取消只作用于尚未开始的任务，操作会留痕。新任务仍按用户轮转插入；可随时恢复公平排序。预估会随渲染和模型响应时间变化。</p>
  {data.audit.length>0&&<details className="queue-audit"><summary>最近的队列操作</summary>{data.audit.map((item,index)=><p key={index}>{new Date(item.created*1000).toLocaleString('zh-CN')} · {owner(item.actor)} · {{cancel:'取消待处理任务',reorder:'调整队列顺序',fair:'恢复公平排序'}[item.action]||item.action}</p>)}</details>}
 </>:<p className="quiet-empty">正在读取制作队列…</p>}</section>
}
