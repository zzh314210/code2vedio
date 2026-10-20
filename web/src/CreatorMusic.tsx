import {useEffect,useRef,useState} from 'react';
import {Check,ChevronRight,Copy,ExternalLink,LoaderCircle,Music2,Pause,Play,Trash2,Upload,Volume2} from 'lucide-react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import {Button} from '@/components/ui/button';
import {request} from './services';
import './music.css';

export type MusicTrack={id:string;title:string;original_title?:string;kind:'preset'|'upload';audio_url:string;duration?:number;description?:string;mood?:string;credit?:string;source_url?:string;license?:string;license_url?:string};
export type MusicSelection={enabled:boolean;volume:number;track:MusicTrack};
export const defaultMusic=():MusicSelection=>({enabled:false,volume:.16,track:{id:'easy-lemon',title:'轻松叙事',kind:'preset',audio_url:'/bgm/easy-lemon.m4a'}});
const clock=(time=0)=>`${Math.floor(time/60)}:${String(Math.floor(time%60)).padStart(2,'0')}`;

export default function CreatorMusic({value,onChange,userId,onLogin}:{value:MusicSelection;onChange:(value:MusicSelection)=>void;userId?:string;onLogin:()=>void}){
 const[open,setOpen]=useState(false),[draft,setDraft]=useState(value),[tab,setTab]=useState<'preset'|'upload'>('preset');
 const[presets,setPresets]=useState<MusicTrack[]>([]),[uploads,setUploads]=useState<MusicTrack[]>([]),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const[playing,setPlaying]=useState(''),[audioLoading,setAudioLoading]=useState(''),[position,setPosition]=useState(0),[length,setLength]=useState(0),[copied,setCopied]=useState(false);
 const player=useRef<HTMLAudioElement>(null),uploadInput=useRef<HTMLInputElement>(null),playRequest=useRef(0);
 const stop=()=>{playRequest.current++;player.current?.pause();setPlaying('');setAudioLoading('');setPosition(0)};
 const refresh=async()=>{
  setLoading(true);setError('');
  const results=await Promise.allSettled([request<{tracks:MusicTrack[]}>('/bgm/catalog.json'),userId?request<MusicTrack[]>('/api/music/uploads'):Promise.resolve([])]);
  if(results[0].status==='fulfilled')setPresets(results[0].value.tracks);
  if(results[1].status==='fulfilled')setUploads(results[1].value);
  const failure=results.find(r=>r.status==='rejected');if(failure?.status==='rejected')setError(failure.reason.message);
  setLoading(false);
 };
 useEffect(()=>{if(open)void refresh();else stop();return()=>{playRequest.current++;player.current?.pause()}},[open,userId]);
 useEffect(()=>{if(player.current)player.current.volume=draft.volume},[draft.volume]);
 const choose=(track:MusicTrack)=>{setDraft({...draft,enabled:true,track});setCopied(false)};
 const preview=async(track:MusicTrack)=>{
  if(playing===track.id||audioLoading===track.id){stop();return}
  stop();setError('');const audio=player.current;if(!audio)return;
  const version=++playRequest.current;setAudioLoading(track.id);setLength(track.duration||0);
  audio.src=track.audio_url;audio.volume=draft.volume;audio.currentTime=0;
  try{await audio.play();if(playRequest.current===version){setPlaying(track.id);setAudioLoading('')}}
  catch(e){if(playRequest.current===version){setAudioLoading('');setError('这首音乐暂时无法试听，请重试或选择其他曲目。')}}
 };
 const upload=async(file?:File)=>{
  if(!file)return;
  if(file.size>30*1024*1024){setError('音乐文件请控制在 30 MB 以内。');return}
  setBusy(true);setError('');const data=new FormData();data.set('file',file);
  try{const track=await request<MusicTrack>('/api/music/uploads',{method:'POST',body:data});setUploads(list=>[track,...list]);choose(track);setTab('upload')}
  catch(e){setError((e as Error).message)}finally{setBusy(false);if(uploadInput.current)uploadInput.current.value=''}
 };
 const remove=async(track:MusicTrack)=>{
  if(!window.confirm(`移除“${track.title}”？已经生成的视频不受影响。`))return;
  setBusy(true);setError('');if(playing===track.id||audioLoading===track.id)stop();
  try{await request('/api/music/uploads/'+track.id,{method:'DELETE'});setUploads(list=>list.filter(t=>t.id!==track.id));if(draft.track.id===track.id){setDraft(defaultMusic());setTab('preset')};if(value.track.id===track.id)onChange(defaultMusic())}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 };
 const selected=[...presets,...uploads].find(t=>t.id===draft.track.id&&t.kind===draft.track.kind)||draft.track;
 const copy=async()=>{try{await navigator.clipboard.writeText(selected.credit||'');setCopied(true)}catch{setError('复制未成功，请在下方署名文字中选择并复制。')}};
 return <>
  <div className={'creator-music'+(value.enabled?' is-enabled':'')}>
   <button type="button" className="music-open" onClick={()=>{setDraft(value);setTab(value.track.kind);setCopied(false);setOpen(true)}} aria-label="选择背景音乐与试听">
    <span className="music-symbol"><Music2 size={18}/></span><span className="music-summary"><strong>背景音乐 <small>{value.enabled?value.track.title:'给画面一点氛围'}</small></strong><span>{value.enabled?'从头播放 · 自动循环 · 人声优先':'可选曲库或上传自己的音乐'}</span></span><ChevronRight size={15}/>
   </button>
   <button type="button" role="switch" aria-checked={value.enabled} aria-label="添加背景音乐" className="music-switch" onClick={()=>onChange({...value,enabled:!value.enabled})}><span/></button>
  </div>
  <Dialog open={open} onOpenChange={next=>{if(!busy)setOpen(next)}}><DialogContent className="music-dialog" onInteractOutside={e=>{if(busy)e.preventDefault()}} onEscapeKeyDown={e=>{if(busy)e.preventDefault()}}>
   <DialogHeader><DialogTitle><Music2 size={21}/>给视频配一点音乐</DialogTitle><DialogDescription>从第一秒播放，自动循环到片尾。旁白出现时，音乐会轻轻让开。</DialogDescription></DialogHeader>
   <div className="music-tabs" role="tablist" aria-label="音乐来源" onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'preset':e.key==='End'?'upload':tab==='preset'?'upload':'preset';setTab(next);document.getElementById('music-'+next+'-tab')?.focus()}}}><button role="tab" id="music-preset-tab" aria-controls="music-track-panel" aria-selected={tab==='preset'} tabIndex={tab==='preset'?0:-1} onClick={()=>setTab('preset')}>精选曲库<span>{presets.length||4}</span></button><button role="tab" id="music-upload-tab" aria-controls="music-track-panel" aria-selected={tab==='upload'} tabIndex={tab==='upload'?0:-1} onClick={()=>setTab('upload')}>我的音乐<span>{uploads.length}</span></button></div>
   {error&&<div className="music-error" role="alert"><span>{error}</span><button onClick={()=>void refresh()} disabled={busy||loading}>重新加载</button></div>}
   <div className="music-tracks" role="tabpanel" id="music-track-panel" aria-labelledby={'music-'+tab+'-tab'}>
    {loading&&presets.length===0?<p className="music-empty"><LoaderCircle className="spin" size={17}/>正在打开曲库…</p>:(tab==='preset'?presets:uploads).map((track,index)=>{
     const active=selected.id===track.id&&selected.kind===track.kind;
     return <article key={track.id} className={'music-track tone-'+index%4+(active?' selected':'')}>
      <div className="music-track-top"><button type="button" className={'music-play'+(playing===track.id?' playing':'')} aria-label={(playing===track.id?'暂停 ':'试听 ')+track.title} onClick={()=>void preview(track)}>{audioLoading===track.id?<LoaderCircle size={18} className="spin"/>:playing===track.id?<Pause size={18} fill="currentColor"/>:<Play size={18} fill="currentColor"/>}</button><button className="music-track-choice" aria-pressed={active} onClick={()=>choose(track)}><strong>{track.title}</strong><small>{track.kind==='preset'?track.original_title:'我的上传'} · {clock(track.duration)}</small></button><button className="music-check" aria-label={'选择 '+track.title} aria-pressed={active} onClick={()=>choose(track)}>{active?<Check size={15}/>:<span/>}</button></div>
      <p>{track.description||'仅你可见 · 已自动平衡音量'}</p><div className="music-track-meta"><span>{track.mood||'本地音乐'}</span>{track.source_url?<a href={track.source_url} target="_blank" rel="noreferrer">来源与署名<ExternalLink size={11}/></a>:<button aria-label={'移除 '+track.title} disabled={busy} onClick={()=>void remove(track)}><Trash2 size={12}/>移除</button>}</div>
     </article>
    })}
    {tab==='upload'&&uploads.length===0&&!loading&&<div className="music-empty"><Music2 size={24}/><strong>把喜欢的音乐带进来</strong><span>个人音乐保留 24 小时，仅自己可见。</span></div>}
   </div>
   {tab==='upload'&&<div className="music-upload"><div><strong>上传自己的 BGM</strong><small>最大 30 MB、15 分钟 · 个人上传保留 24 小时</small></div><Button variant="outline" disabled={busy} onClick={()=>userId?uploadInput.current?.click():(setOpen(false),onLogin())}>{busy?<LoaderCircle size={15} className="spin"/>:<Upload size={15}/>} {busy?'正在处理…':userId?'上传音乐':'登录后上传'}</Button><input ref={uploadInput} type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,.aac" hidden aria-label="上传背景音乐文件" onChange={e=>void upload(e.target.files?.[0])}/></div>}
   <div className="music-volume"><div><label htmlFor="bgm-volume"><Volume2 size={16}/>背景音量</label><output htmlFor="bgm-volume">{Math.round(draft.volume*100)}%</output></div><input id="bgm-volume" style={{background:`linear-gradient(to right,#7979c6 ${draft.volume*200}%,#e1e4f0 ${draft.volume*200}%)`}} type="range" min="0" max="50" step="1" value={Math.round(draft.volume*100)} onChange={e=>setDraft({...draft,volume:Number(e.target.value)/100})}/><small>建议 10–20%，突出人声。试听使用当前音量。</small></div>
   {(playing||audioLoading)&&<div className="music-playback"><span className="audio-bars" aria-hidden="true"><i/><i/><i/><i/></span><span>{[...presets,...uploads].find(t=>t.id===(playing||audioLoading))?.title}</span><input type="range" min="0" max={Math.max(1,length)} step=".1" value={Math.min(position,length)} aria-label="音乐试听进度" onChange={e=>{if(player.current){player.current.currentTime=Number(e.target.value);setPosition(Number(e.target.value))}}}/><small>{clock(position)} / {clock(length)}</small></div>}
   {selected.credit&&<details className="music-credit"><summary>免费可商用 · 发布时请附上音乐署名</summary><p>{selected.credit}</p><button onClick={()=>void copy()}><Copy size={13}/>{copied?'已复制':'复制音乐署名'}</button></details>}
   <div className="music-dialog-actions"><button className="music-disable" disabled={busy} onClick={()=>{onChange({...value,enabled:false});setOpen(false)}}>不添加音乐</button><Button disabled={busy||loading||!selected.duration} onClick={()=>{onChange({...draft,track:selected,enabled:true});setOpen(false)}}><Check size={16}/>使用这首音乐</Button></div>
   <audio ref={player} preload="none" onTimeUpdate={()=>setPosition(player.current?.currentTime||0)} onLoadedMetadata={()=>setLength(player.current?.duration||0)} onEnded={stop} onError={()=>{if(playing||audioLoading){stop();setError('音乐加载中断，请重试试听。')}}}/>
  </DialogContent></Dialog>
 </>
}
