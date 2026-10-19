import {useState} from 'react';
import {Headphones,ChevronRight,Check,LoaderCircle} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import VoicePicker from './VoicePicker';
import {request,jsonRequest} from './services';
import type {Config} from './AccountPages';
export default function CreatorVoice({config,onSave}:{config:Config|null;onSave:(value:Config)=>void}){
 const[open,setOpen]=useState(false),[voice,setVoice]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 if(!config||config.tts.provider!=='edge')return null;
 const save=async()=>{setBusy(true);setError('');try{onSave(await request<Config>('/api/config',jsonRequest('POST',{...config,tts:{...config.tts,voice}})));setOpen(false)}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <><button type="button" className="creator-voice" onClick={()=>{setVoice(config.tts.voice||'zh-CN-XiaoxiaoNeural');setOpen(true)}}><span><Headphones size={18}/><strong>视频配音</strong></span><span>{config.tts.voice?.replace(/Neural$/,'').split('-').slice(-1)[0]}<small>免费 · 更换与试听</small><ChevronRight size={15}/></span></button><Dialog open={open} onOpenChange={setOpen}><DialogContent className="voice-dialog"><DialogHeader><DialogTitle>给这支视频挑选声音</DialogTitle><DialogDescription>听一听，再选择。此处均为免费在线音色。</DialogDescription></DialogHeader><VoicePicker value={voice} onChange={setVoice}/>{error&&<p className="editor-error" role="alert">{error}</p>}<Button onClick={save} disabled={busy}>{busy?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>}应用此音色</Button></DialogContent></Dialog></>
}
