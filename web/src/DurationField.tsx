import {useEffect, useId, useState} from 'react';
import {Clock3, Minus, Plus} from 'lucide-react';

export default function DurationField({value,onChange,label='视频时长',min=15,max=180}:{value:number;onChange:(value:number)=>void;label?:string;min?:number;max?:number}) {
  const id=useId();
  const [draft,setDraft]=useState(String(value));
  useEffect(()=>setDraft(String(value)),[value]);
  const commit=()=>{const parsed=Number(draft);const next=draft.trim()&&Number.isFinite(parsed)?Math.max(min,Math.min(max,Math.round(parsed))):value;setDraft(String(next));onChange(next)};
  const invalid=Boolean(draft)&&(!Number.isInteger(Number(draft))||Number(draft)<min||Number(draft)>max);
  return <div className="duration-field"><label htmlFor={id}>{label}</label><div className="duration-control"><Clock3 size={17} aria-hidden="true"/><button type="button" disabled={value<=min} aria-label={'减少'+label} onClick={()=>onChange(Math.max(min,value-5))}><Minus size={13}/></button><input id={id} type="number" inputMode="numeric" min={min} max={max} step={1} value={draft} aria-describedby={id+'-hint'} aria-invalid={invalid} onChange={e=>{setDraft(e.target.value);const n=Number(e.target.value);if(e.target.value&&Number.isInteger(n)&&n>=min&&n<=max)onChange(n)}} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();commit()}}}/><span>秒</span><button type="button" disabled={value>=max} aria-label={'增加'+label} onClick={()=>onChange(Math.min(max,value+5))}><Plus size={13}/></button></div><small id={id+'-hint'} className={invalid?'duration-hint invalid':'duration-hint'}>{invalid?`请输入 ${min}–${max} 之间的整数，离开时自动调整。`:`自由填写 · ${min}–${max} 秒${max===180?'，最长 3 分钟':''}`}</small></div>;
}
