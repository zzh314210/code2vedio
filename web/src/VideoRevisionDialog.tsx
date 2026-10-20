import {QueueStatus,type QueueState} from './QueueStatus';
import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,LoaderCircle,ScanEye,Sparkles} from 'lucide-react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import {Button} from '@/components/ui/button';
import {Textarea} from '@/components/ui/textarea';
import {request,jsonRequest} from './services';
import './revision.css';

type Film={id:string;prompt:string;revision_number?:number};
type Suggestion={title:string;reason:string;feedback:string};
type Advice={status:'idle'|'queued'|'running'|'ready'|'failed';summary?:string;suggestions?:Suggestion[];message?:string;queue?:QueueState};
export default function VideoRevisionDialog({job,onClose,onCreated}:{job:Film|null;onClose:()=>void;onCreated:(id:string)=>void}){
 const[feedback,setFeedback]=useState(''),[confirmPlan,setConfirmPlan]=useState(true),[busy,setBusy]=useState(false),[reviewBusy,setReviewBusy]=useState(false),[error,setError]=useState(''),[advice,setAdvice]=useState<Advice>({status:'idle'}),[used,setUsed]=useState<number[]>([]);
 const requestId=useRef(crypto.randomUUID()),currentJob=useRef(job?.id);currentJob.current=job?.id;
 useEffect(()=>{if(!job)return;setFeedback('');setConfirmPlan(true);setError('');setAdvice({status:'idle'});setUsed([]);requestId.current=crypto.randomUUID();let live=true;
  request<Advice>('/api/jobs/'+job.id+'/revision-advice').then(value=>{if(live)setAdvice(value)}).catch(()=>{});return()=>{live=false};
 },[job?.id]);
 const checking=advice.status==='queued'||advice.status==='running';
 useEffect(()=>{if(!job||!checking)return;let live=true;const timer=setInterval(()=>{request<Advice>('/api/jobs/'+job.id+'/revision-advice').then(value=>{if(live)setAdvice(value)}).catch(e=>{if(live){setAdvice({status:'failed',message:(e as Error).message})}})},2500);return()=>{live=false;clearInterval(timer)}},[job?.id,checking]);
 const change=(value:string)=>{setFeedback(value);requestId.current=crypto.randomUUID()};
 const review=async()=>{if(!job||checking||reviewBusy)return;const id=job.id;setReviewBusy(true);setError('');try{const value=await request<Advice>('/api/jobs/'+id+'/revision-advice',jsonRequest('POST',{}));if(currentJob.current===id){setAdvice(value);setUsed([])}}catch(e){if(currentJob.current===id)setError((e as Error).message)}finally{setReviewBusy(false)}};
 const apply=(suggestion:Suggestion,index:number)=>{const next=[feedback.trim(),suggestion.feedback].filter(Boolean).join('\n\n');if(next.length>6000){setError('修改要求已接近字数上限，请先精简输入。');return}change(next);setUsed(values=>[...values,index]);setError('')};
 const submit=async()=>{if(!job||busy)return;setBusy(true);setError('');try{const result=await request<{id:string}>('/api/jobs/'+job.id+'/revisions',jsonRequest('POST',{feedback:feedback.trim(),auto_approve:!confirmPlan,request_id:requestId.current}));onCreated(result.id)}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <Dialog open={Boolean(job)} onOpenChange={open=>{if(!open&&!busy)onClose()}}><DialogContent className="revision-dialog" onEscapeKeyDown={e=>{if(busy)e.preventDefault()}} onPointerDownOutside={e=>{if(busy)e.preventDefault()}}><DialogHeader><DialogTitle>让这支视频，再好一点</DialogTitle><DialogDescription>描述想改的地方，调整分镜后生成新版本。原片会保留，随时可以对比。</DialogDescription></DialogHeader>
  <div className="revision-scroll">
  <div className="revision-source"><span>基于第 {job?.revision_number||1} 版</span><p>{job?.prompt}</p></div>
  <div className="revision-editor-label"><label htmlFor="film-revision-feedback">想修改哪里？</label><Button variant="outline" onClick={review} disabled={checking||reviewBusy||busy}>{checking||reviewBusy?<LoaderCircle size={15} className="spin"/>:<ScanEye size={15}/>}AI 帮我看看</Button></div>
  <Textarea id="film-revision-feedback" value={feedback} onChange={e=>change(e.target.value)} maxLength={6000} disabled={busy} placeholder="例如：开头缩短一点；第二段先用动画解释，再出现公式；结尾留两秒让我回忆答案。" rows={5}/>
  <div className="revision-input-note"><span>AI 建议会使用已配置的视觉模型；点击后才开始审核。</span><span>{feedback.length}/6000</span></div>
  {advice.status==='queued'&&<QueueStatus queue={advice.queue}/>}
  {advice.status==='running'&&<div className="revision-review-state" role="status"><LoaderCircle size={17} className="spin"/><span>正在查看画面与分镜，通常需要几十秒。可以先填写自己的意见。</span></div>}
  {advice.status==='failed'&&<p className="revision-review-error" role="status">{advice.message} 你也可以直接填写修改要求。</p>}
  {advice.status==='ready'&&<section className="revision-advice" aria-label="AI 修改建议"><p>{advice.summary}</p>{advice.suggestions?.map((suggestion,index)=><article key={index}><div><strong>{suggestion.title}</strong><p>{suggestion.reason}</p></div><Button variant="outline" disabled={used.includes(index)||busy} onClick={()=>apply(suggestion,index)}>{used.includes(index)?<><Check size={14}/>已填入</>:<>采用建议<ArrowRight size={14}/></>}</Button></article>)}</section>}
  <label className="revision-confirm"><input type="checkbox" checked={confirmPlan} onChange={e=>{setConfirmPlan(e.target.checked);requestId.current=crypto.randomUUID()}} disabled={busy}/><span><strong>制作前，先让我确认修改后的分镜</strong><small>可以继续微调旁白与画面描述，满意后再开始制作。</small></span></label>
  {error&&<p className="revision-error" role="alert">{error}</p>}
  </div>
  <div className="revision-actions"><Button variant="outline" onClick={onClose} disabled={busy}>取消</Button><Button onClick={submit} disabled={busy||feedback.trim().length<2}>{busy?<LoaderCircle size={16} className="spin"/>:<Sparkles size={16}/>}生成修改版</Button></div>
 </DialogContent></Dialog>
}
