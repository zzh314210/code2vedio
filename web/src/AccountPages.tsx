import {type Channel} from './ModelChannel';
import {useEffect,useState} from 'react';
import {Check,Monitor,LogOut} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {request,jsonRequest,date,type User} from './services';

export type Config={use_platform?:boolean;saved?:boolean;platform_text_model?:string;platform_vision_model?:string;text:Channel;vision:Channel;vision_inherit:boolean;tts:Channel;text_ready:boolean;vision_ready:boolean;speech_ready:boolean};
function Notice({error,message}:{error:string;message?:string}){return <>{error&&<p className="editor-error" role="alert">{error}</p>}{message&&<p className="success-notice" role="status"><Check size={16}/>{message}</p>}</>}

export {default as WalletPage} from './WalletPage';
export {default as AdminPage} from './AdminPage';

type Session={id:string;created_at:number;expires_at:number;agent:string;current:boolean};
export function AccountPage({user,onLogout}:{user:User;onLogout:()=>Promise<void>}){
 const[sessions,setSessions]=useState<Session[]>([]),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>request<Session[]>('/api/auth/sessions').then(setSessions).catch(e=>setError(e.message));useEffect(()=>{void load()},[]);
 const password=async(e:React.FormEvent<HTMLFormElement>)=>{e.preventDefault();const form=e.currentTarget;const data=Object.fromEntries(new FormData(form));if(data.new_password!==data.confirm){setError('两次新密码不一致。');return}setBusy(true);setError('');setMessage('');try{await request('/api/auth/password',jsonRequest('PUT',data));form.reset();setMessage('密码已更新，其他设备已退出登录。');await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <div className="account-layout page-enter"><section className="settings-card"><h2>账号信息</h2><dl className="profile-details"><div><dt>昵称</dt><dd>{user.display_name}</dd></div><div><dt>登录账号</dt><dd>{user.username}</dd></div><div><dt>账户类型</dt><dd>{user.role==='admin'?'管理员':'创作者'}</dd></div><div><dt>加入时间</dt><dd>{date(user.created_at)}</dd></div></dl><Button variant="outline" className="account-signout" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await onLogout()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><LogOut size={16}/>退出登录</Button></section><section className="settings-card"><h2>修改密码</h2><form onSubmit={password} className="stack-form"><label>当前密码<Input name="current_password" type="password" autoComplete="current-password" required maxLength={128}/></label><label>新密码<Input name="new_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} placeholder="至少10位…"/></label><label>确认新密码<Input name="confirm" type="password" autoComplete="new-password" required minLength={10} maxLength={128}/></label><Button type="submit" disabled={busy}>{busy?'正在更新…':'更新密码并撤销其他登录'}</Button></form></section><section className="settings-card wide"><h2>登录设备</h2><p>登录状态有效期为7天。可以退出不认识的登录设备。</p><Notice error={error} message={message}/><ul className="session-list">{sessions.map(s=><li key={s.id}><Monitor size={22}/><div><strong>{s.current?'当前设备':'其他登录设备'}</strong><p>{s.agent||'未知浏览器'}</p><small>{date(s.created_at)} 登录 · {date(s.expires_at)} 到期</small></div>{s.current?<span className="pill success">使用中</span>:<Button variant="outline" onClick={async()=>{if(!window.confirm('撤销此设备的登录凭证？'))return;try{await request('/api/auth/sessions/'+s.id,{method:'DELETE'});await load()}catch(e){setError((e as Error).message)}}}>撤销登录</Button>}</li>)}</ul></section></div>
}
