import {QueueStatus,type QueueState} from './QueueStatus';
import {Check,Clock3,LoaderCircle,PauseCircle} from 'lucide-react';
import {Progress} from '@/components/ui/progress';
export type ProgressJob={id:string;duration:number;status:string;stage:string;stage_status?:string;auto_approve?:boolean;stage_started_at?:number;created_at?:number;queue?:QueueState};
const stages=[['outline','整理大纲'],['storyboard','编排分镜'],['criteria','制定标准'],['audio','合成配音'],['assets','整理素材'],['code','制作动画'],['render','渲染画面'],['review','检查画面'],['compose','合成成片'],['acceptance','成片验收']];
// Coarse budgets, not a promised delivery time. Rendering/revision dominates.
const weights=[.06,.09,.06,.06,.01,.19,.20,.13,.05,.15];
export function estimateMinutes(duration:number){return duration<=45?[12,35]:duration<=90?[20,55]:duration<=120?[30,75]:duration<=180?[40,100]:[60,140]}
export default function GenerationProgress({job,compact=false}:{job:ProgressJob;compact?:boolean}){
 const index=stages.findIndex(([id])=>id===job.stage),known=index>=0,i=Math.max(0,index);
 const paused=job.status==='awaiting_review',queued=job.status==='queued',failed=job.status==='failed',complete=job.status==='complete';
 const before=weights.slice(0,i).reduce((a,b)=>a+b,0);
 const progress=complete?100:queued||!known?0:Math.round((before+weights[i]*(job.stage_status==='complete'?1:.25))*100);
 const total=estimateMinutes(job.duration),remaining=total.map(n=>Math.max(1,Math.ceil(n*(1-before))));
 const longStage=Boolean(job.stage_started_at&&Date.now()/1000-job.stage_started_at>total[1]*60*weights[i]);
 const title=complete?'成片已完成':failed?'制作暂停，请查看错误后重试':paused?'等待你确认'+(job.stage==='outline'?'大纲':'分镜'):queued?'排队中':known?'正在'+stages[i][1]:'正在准备制作';
 return <section className={'generation-progress '+(compact?'compact':'')} aria-label="视频生成进度">
  <div className="generation-progress-heading">{complete?<Check size={18}/>:paused||failed?<PauseCircle size={18}/>:<LoaderCircle className="spin" size={18}/>}<strong>{title}</strong><span>{complete?'100%':`约 ${progress}%`}</span></div>
  <Progress value={progress} aria-label="估算生成进度"/>
  <p className="generation-eta"><Clock3 size={15}/>{complete?'前往我的作品预览、下载':failed?'任务已保存，不会自动重复提交':paused?'确认后继续；等待期间不计入制作预估':queued?`开始后预计 ${total[0]}–${total[1]} 分钟`:longStage?'本步骤耗时较长，正在继续处理，完成时间可能延后':`预计还需 ${remaining[0]}–${remaining[1]} 分钟`}</p>
  {queued&&<QueueStatus queue={job.queue} cancelPath={'/api/jobs/'+job.id+'/cancel'}/>}
  {!compact&&<ol className="pipeline-steps">{stages.map(([id,label],n)=><li key={id} aria-current={!complete&&n===index?'step':undefined} className={complete||n<index?'done':''}><span>{complete||n<index?<Check size={12}/>:n+1}</span>{label}</li>)}</ol>}
  {!compact&&!complete&&!failed&&<p className="generation-disclaimer">按制作步骤估算，复杂动画、排队和自动修正可能延长时间。{!job.auto_approve?'大纲与分镜需你确认后才会继续。':'无需人工确认大纲与分镜，可离开页面，稍后到「我的作品」领取。'}</p>}
 </section>
}
