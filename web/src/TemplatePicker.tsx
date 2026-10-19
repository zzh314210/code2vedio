import {useEffect,useState} from 'react';
import {ArrowUpRight,BookOpen,Check,Clapperboard,Lightbulb,Map,Play,Shapes,ShoppingBag,Sigma,SpellCheck} from 'lucide-react';
import {Button} from '@/components/ui/button';
import ShowcaseDialog,{samples} from './ShowcaseDialog';
import templates from '../../templates/catalog.json';
export {templates};
const templateIcons:Record<string,typeof Shapes>={explainer:Lightbulb,history_map:Map,math_visual:Sigma,word_story:SpellCheck,documentary:Clapperboard,product:ShoppingBag,notes:BookOpen};
export default function TemplatePicker({selected,onSelect,onExample,notesOnly=false}:{selected:string;onSelect:(id:string)=>void;onExample:(id:string)=>void;notesOnly?:boolean}){
 const current=templates.find(t=>t.id===selected);const[category,setCategory]=useState(current?.category||'learning'),[preview,setPreview]=useState('');
 useEffect(()=>{const t=templates.find(t=>t.id===selected);if(t)setCategory(t.category)},[selected]);
 const shown=templates.filter(t=>notesOnly?t.id==='notes':t.category===category);
 return <section className={'template-picker'+(notesOnly?' notes-template-picker':'')} aria-label="创作模板">
  <div className="template-heading"><div><Shapes size={17}/><h2>{notesOnly?'笔记变成课，复盘更轻松':'选一种讲法，让内容更有章法'}</h2></div>{!notesOnly&&<div className="template-categories" aria-label="模板分类">{[['learning','讲清知识'],['story','故事与产品'],['review','笔记复盘']].map(([id,name])=><button key={id} aria-pressed={category===id} onClick={()=>setCategory(id)}>{name}</button>)}</div>}</div>
  <div className="template-grid">{shown.map(t=>{const Icon=templateIcons[t.id]||Shapes;return <article key={t.id} data-template={t.id} className={selected===t.id?'selected':''}>
   <button className="template-select" aria-pressed={selected===t.id} onClick={()=>onSelect(t.id)}>
    <span className="template-icon" aria-hidden="true"><Icon size={20} strokeWidth={1.8}/></span>
    <span className="template-copy"><span className="template-title"><strong>{t.title}</strong></span><span className="template-tagline">{t.tagline}</span></span>
    <span className="template-selection" aria-hidden="true">{selected===t.id&&<Check size={12} strokeWidth={2.5}/>}</span>
   </button>
   <div className="template-card-actions">{samples.some(s=>s.id===t.id)&&<button onClick={()=>setPreview(t.id)} aria-label={'观看'+t.title+'的真实示例'}><Play size={12}/>看示例</button>}<button onClick={()=>onExample(t.id)} aria-label={'填入'+t.title+'的示例需求'}>填入示例<ArrowUpRight size={12}/></button></div>
  </article>})}</div>
  {current&&<div className="template-detail" aria-live="polite"><p>{current.description}</p><p className="template-structure"><span>本片结构</span>{current.structure.map((s,i)=><span key={s}>{i>0&&<b>→</b>}{s}</span>)}</p></div>}
  <ShowcaseDialog id={preview} onClose={()=>setPreview('')}><Button onClick={()=>{onExample(preview);setPreview('')}}>用这个模板开始<ArrowUpRight size={15}/></Button></ShowcaseDialog>
 </section>
}
