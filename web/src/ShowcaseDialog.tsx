import {useState} from 'react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import samples from '../../templates/showcase.json';
export {samples};
export default function ShowcaseDialog({id,onClose,children}:{id:string;onClose:()=>void;children?:React.ReactNode}){
 const sample=samples.find(s=>s.id===id);const[failed,setFailed]=useState('');
 return <Dialog open={Boolean(sample)} onOpenChange={open=>{if(!open)onClose()}}><DialogContent className="template-demo-dialog"><DialogHeader><DialogTitle>{sample?.title}</DialogTitle><DialogDescription>{sample?.description}</DialogDescription></DialogHeader>{sample&&<><video key={id} src={'/showcase/'+id+'.mp4'} poster={'/showcase/'+id+'.jpg'} controls playsInline preload="metadata" aria-label="实际成片示例" onError={()=>setFailed(id)} onLoadedData={()=>setFailed('')}/>{failed===id&&<p role="alert">视频暂时无法播放，请稍后重试，或<a href={'/showcase/'+id+'.mp4'} download>下载查看</a>。</p>}<p className="sample-credit">{sample.credit} · {sample.license}{sample.source&&<> · <a href={sample.source} target="_blank" rel="noreferrer">查看来源与许可</a></>}</p></>}{children}</DialogContent></Dialog>
}
