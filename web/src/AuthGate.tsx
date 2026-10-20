import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,Film,LoaderCircle,ShieldCheck,Layers3} from 'lucide-react';
import App from './App';
import PelicanLogo from './PelicanLogo';
import {request,jsonRequest,type User} from './services';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';

type AuthMode='login'|'register';
const privateViews=new Set(['library','config','wallet','account','admin','api']);
const route=()=>location.hash.slice(1);

export default function AuthGate(){
 const [user,setUser]=useState<User|null>(null);
 const [mode,setMode]=useState<AuthMode>(route()==='register'?'register':'login');
 const [open,setOpen]=useState(['login','register'].includes(route()));
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[reason,setReason]=useState('');
 const [workspaceKey,setWorkspaceKey]=useState(0);
 const userRef=useRef(user),sessionReady=useRef(false);
 const bootstrap=useRef<AbortController|null>(null);
 const returnTo=useRef(privateViews.has(route())?route():'create');
 const heading=useRef<HTMLHeadingElement>(null);
 userRef.current=user;

 const showLogin=(message:string,target='create',nextMode:AuthMode='login')=>{
  returnTo.current=privateViews.has(target)||['create','edit','notes'].includes(target)?target:'create';
  setReason(message);setError('');setMode(nextMode);setOpen(true);
  location.hash=nextMode;
  window.scrollTo({top:0});
 };
 const navigate=(target:string)=>{history.replaceState(null,'','#'+target);window.dispatchEvent(new HashChangeEvent('hashchange'))};
 const closeLogin=()=>{setOpen(false);setError('');returnTo.current='create';navigate('create');requestAnimationFrame(()=>document.getElementById('prompt')?.focus({preventScroll:true}))};
 const signedIn=(next:User)=>{
  bootstrap.current?.abort();sessionReady.current=true;
  userRef.current=next;setUser(next);setError('');setOpen(false);
  // Keep the mounted workspace and its draft. Login never submits a paid job.
  navigate(returnTo.current);
 };
 useEffect(()=>{
  let live=true;const controller=new AbortController();bootstrap.current=controller;
  request<User>('/api/auth/me',{signal:controller.signal}).then(next=>{
   if(!live||controller.signal.aborted)return;
   userRef.current=next;setUser(next);
   if(['login','register'].includes(route())){setOpen(false);location.hash=returnTo.current}
  }).catch(()=>{
   if(live&&!controller.signal.aborted&&!userRef.current&&privateViews.has(route()))showLogin('登录后进入你的个人工作空间。',route());
  }).finally(()=>{if(live)sessionReady.current=true});
  const changed=()=>{
   const next=route();
   if(next==='login'||next==='register'){
    if(userRef.current){setOpen(false);navigate(returnTo.current);return}
    setMode(next);setOpen(true);setError('');
   }else if(privateViews.has(next)&&!userRef.current&&sessionReady.current){
    showLogin('登录后进入你的个人工作空间。',next);
   }else setOpen(false);
  };
  const expired=()=>{
   if(!userRef.current)return;
   userRef.current=null;setUser(null);setWorkspaceKey(key=>key+1);
   showLogin('登录已过期，请重新登录后继续。',privateViews.has(route())?route():'create');
  };
  window.addEventListener('hashchange',changed);
  window.addEventListener('frame-session-expired',expired);
  return()=>{live=false;controller.abort();window.removeEventListener('hashchange',changed);window.removeEventListener('frame-session-expired',expired)};
 },[]);
 useEffect(()=>{if(open){heading.current?.focus();window.scrollTo({top:0})}},[open]);
 const submit=async(e:React.FormEvent<HTMLFormElement>)=>{
  e.preventDefault();
  const data=Object.fromEntries(new FormData(e.currentTarget));
  if(mode==='register'&&data.password!==data.confirm){setError('两次密码不一致，请重新输入。');return}
  setBusy(true);setError('');
  try{signedIn(await request<User>('/api/auth/'+mode,jsonRequest('POST',data)))}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 };
 const logout=async()=>{
  bootstrap.current?.abort();
  await request('/api/auth/logout',{method:'POST'});
  userRef.current=null;setUser(null);setWorkspaceKey(key=>key+1);
  closeLogin();
 };
 return <>
  <div hidden={open}>
   <App key={workspaceKey} user={user} onUserChange={setUser} onLogout={logout} onLogin={showLogin}/>
  </div>
  {open&&<main className="auth-page"><section className="auth-story">
   <a className="wordmark workspace-wordmark" href="#create" onClick={e=>{e.preventDefault();closeLogin()}}><PelicanLogo/><span className="pelican-wordmark"><strong>鹈鹕先生</strong><small>的视频站</small></span></a>
   <div><span className="eyebrow">从想法到作品</span><h1>把内容讲清楚。<br/>把灵感留下来。</h1><p>策划、分镜、配音与动画，在一个属于你的空间里完成。</p><div className="auth-illustration" aria-hidden="true"><span><Layers3 size={46}/></span><i/><span><Film size={46}/></span></div></div>
   <p className="auth-trust"><ShieldCheck size={17}/>独立作品空间 · 个人 API 配置</p>
  </section><section className="auth-card">
   <button type="button" className="auth-back" onClick={closeLogin}><ArrowLeft size={16}/>返回创作面板</button>
   <span className="eyebrow">你的创作，从这里开始</span><h2 ref={heading} tabIndex={-1}>{mode==='login'?'欢迎回来':'创建你的账号'}</h2>
   <p>{reason||(mode==='login'?'登录后，继续你的创作。':'注册即可拥有独立的作品与素材空间。')}</p>
   <p className="auth-draft-note"><ShieldCheck size={15}/>已填写的需求和视频参数会保留，登录后可继续编辑。</p>
   <div className="auth-tabs" aria-label="登录方式"><button aria-pressed={mode==='login'} onClick={()=>{setMode('login');setError('');history.replaceState(null,'','#login')}}>登录</button><button aria-pressed={mode==='register'} onClick={()=>{setMode('register');setError('');history.replaceState(null,'','#register')}}>注册</button></div>
   <form onSubmit={submit} key={mode} className="stack-form">
    {mode==='register'&&<label>昵称<Input name="display_name" autoComplete="nickname" maxLength={60} placeholder="怎么称呼你…"/></label>}
    <label>账号<Input name="username" autoComplete="username" spellCheck={false} required minLength={3} maxLength={80} pattern="[A-Za-z0-9][A-Za-z0-9_.@+\-]{2,79}" placeholder="用户名或邮箱…"/></label>
    <label>密码<Input name="password" type="password" autoComplete={mode==='login'?'current-password':'new-password'} required minLength={mode==='register'?10:1} maxLength={128} placeholder={mode==='register'?'至少10位，建议组合字母和数字…':'输入你的密码…'}/></label>
    {mode==='register'&&<label>确认密码<Input name="confirm" type="password" autoComplete="new-password" required minLength={10} maxLength={128} placeholder="再次输入密码…"/></label>}
    {error&&<p className="editor-error" role="alert">{error}</p>}
    <Button type="submit" disabled={busy} className="primary-action">{busy?<LoaderCircle className="spin" size={17}/>:<ArrowRight size={17}/>} {busy?'正在处理…':mode==='login'?'登录工作空间':'注册并开始创作'}</Button>
   </form><p className="form-hint">{mode==='register'?'请妥善保存账号密码；邮箱格式账号仅用作登录名。':'忘记密码？请联系站点管理员协助恢复。'}</p>
  </section></main>}
 </>;
}
