import {useEffect,useState} from 'react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import samples from '../../templates/showcase.json';
export {samples};
export default function ShowcaseDialog({id,onClose,children}:{id:string;onClose:()=>void;children?:React.ReactNode}){
 const[active,setActive]=useState(id),[failed,setFailed]=useState('');
 useEffect(()=>setActive(id),[id]);
 const primary=samples.find(s=>s.id===id),sample=samples.find(s=>s.id===active)||primary;
 const related=samples.filter(s=>s.id===id||s.id.startsWith(id+'_'));
 return <Dialog open={Boolean(primary)} onOpenChange={open=>{if(!open)onClose()}}><DialogContent className="template-demo-dialog"><DialogHeader><DialogTitle>{sample?.title}</DialogTitle><DialogDescription>{sample?.description}</DialogDescription></DialogHeader>{related.length>1&&<div className="sample-variants" role="tablist" aria-label="示例题型">{related.map(s=><button key={s.id} role="tab" aria-selected={sample?.id===s.id} onClick={()=>setActive(s.id)}>{s.id===id?'先找矛盾 · 练习':'假设排除 · 真题'}</button>)}</div>}{sample&&<><video key={sample.id} src={'/showcase/'+sample.id+'.mp4'} poster={'/showcase/'+sample.id+'.jpg'} controls playsInline preload="metadata" aria-label="实际成片示例" onError={()=>setFailed(sample.id)} onLoadedData={()=>setFailed('')}/>{failed===sample.id&&<p role="alert">视频暂时无法播放，请稍后重试，或<a href={'/showcase/'+sample.id+'.mp4'} download>下载查看</a>。</p>}<p className="sample-credit">{sample.credit} · {sample.license}{sample.source&&<> · <a href={sample.source} target="_blank" rel="noreferrer">查看来源与许可</a></>}</p></>}{children}</DialogContent></Dialog>
}
