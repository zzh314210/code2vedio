import {useCallback,useEffect,useRef} from 'react';
import {CircleHelp} from 'lucide-react';
import {driver,type Driver,type DriveStep} from 'driver.js';
import 'driver.js/dist/driver.css';
import './guide.css';

const seenInMemory=new Set<string>();
const storageKey=(id:string)=>`frame.guide.v1.${id}`;
const hasSeen=(key:string)=>{
  if(seenInMemory.has(key))return true;
  try{return localStorage.getItem(key)==='seen'}catch{return false}
};
const remember=(key:string)=>{
  seenInMemory.add(key);
  try{localStorage.setItem(key,'seen')}catch{/* The guide also works when storage is unavailable. */}
};
const visibleTarget=(selector:string)=>()=>
  Array.from(document.querySelectorAll(selector)).find(el=>el.getBoundingClientRect().width>0) || document.querySelector('#prompt')!;
const responsiveTarget=(desktop:string,mobile:string)=>()=>
  document.querySelector(window.innerWidth<=700?mobile:desktop)!;

export default function StudioGuide({userId,enabled,ready}:{userId?:string;enabled:boolean;ready:boolean}){
  const instance=useRef<Driver|null>(null);
  const closeTour=useRef<(()=>void)|null>(null);
  const button=useRef<HTMLButtonElement>(null);
  const start=useCallback(()=>{
    if(instance.current?.isActive()||!button.current?.getBoundingClientRect().width)return;
    const key=storageKey(userId||'guest');
    const scrollY=window.scrollY;
    let finished=false;
    let moving=false;
    let cleaned=false;
    // Keep keyboard activation inside the explanation, away from real actions.
    const trapTab=(event:KeyboardEvent)=>{
      if(event.key!=='Tab')return;
      const controls=Array.from(document.querySelectorAll<HTMLButtonElement>('.studio-guide button'))
        .filter(el=>!el.disabled&&!el.classList.contains('driver-popover-btn-disabled')&&el.getBoundingClientRect().width>0);
      if(!controls.length)return;
      event.preventDefault();event.stopImmediatePropagation();
      const current=controls.indexOf(document.activeElement as HTMLButtonElement);
      controls[(current+(event.shiftKey?-1:1)+controls.length)%controls.length].focus();
    };
    const cleanup=()=>{
      if(cleaned)return;
      cleaned=true;
      document.removeEventListener('keydown',trapTab,true);
      window.removeEventListener('resize',fitCompact);
      document.body.style.removeProperty('--guide-accent');
      remember(key);instance.current=null;closeTour.current=null;
      requestAnimationFrame(()=>{
        if(!button.current?.getBoundingClientRect().width)return;
        if(finished){document.getElementById('prompt')?.focus()}
        else{window.scrollTo({top:scrollY,behavior:'instant'});button.current.focus({preventScroll:true})}
      });
    };
    // driver.js may omit onDestroyed if closed before its first animation ends.
    const close=()=>{tour.destroy();cleanup()};
    const fitCompact=()=>requestAnimationFrame(()=>{
      if(cleaned||window.innerWidth>700)return;
      const popover=document.querySelector('.studio-guide');
      const target=tour.getActiveElement();
      if(!popover||!target)return;
      const card=popover.getBoundingClientRect(),rect=target.getBoundingClientRect();
      const top=Math.max(14,(card.top-24-rect.height)/2);
      window.scrollTo({top:Math.max(0,window.scrollY+rect.top-top),behavior:'instant'});
      tour.refresh();
    });
    const content=[
      {tone:'model',color:'#334155',label:'模型配置',title:'连接你的模型服务',element:visibleTarget('[data-guide="config"]'),
        action:userId?'打开「配置」，填好这三项':'登录后打开「配置」',
        detail:'<div class="guide-tokens"><span>接口地址</span><span>API Key</span><span>模型名称</span></div>',
        note:'内容生成、视觉审核分别配置。模型可手填或从列表选择。'},
      {tone:'brief',color:'#1d4ed8',label:'创作需求',title:'说清你想做什么视频',element:'#prompt',
        action:'写主题、受众和讲解重点',
        detail:'<p>例如：给初学者讲复利，用曲线对比单利与复利。</p>',
        note:'也可以先点下方示例，再改成自己的需求。'},
      {tone:'source',color:'#0f766e',label:'参考素材 · 可选',title:'补充素材，让内容更准确',element:responsiveTarget('.source-form','.source-query'),
        action:'搜索后，再选为本片参考',
        detail:'<div class="guide-flow"><span>搜索素材</span><b>→</b><span>预览正文</span><b>→</b><span>选为参考</span></div>',
        note:'也可上传文件。只有选中的正文会加入本片参考。'},
      {tone:'style',color:'#6d28d9',label:'风格与配音',title:'选择风格和声音',element:responsiveTarget('.output-fields','.creator-voice'),
        action:'选好时长、横竖屏和配音',
        detail:'<p>点击「视频配音」选择音色，先试听 2 秒。</p>',
        note:'在「视频创作」的「视频风格」中选择画风。'},
      {tone:'review',color:'#92400e',label:'确认与制作',title:'先确认内容，再制作',element:'.generate-button',
        action:'点击生成，先看大纲',
        detail:'<div class="guide-flow"><span>确认大纲</span><b>→</b><span>确认分镜</span><b>→</b><span>制作成片</span></div>',
        note:'每一步都能修改。勾选「免审核」可自动完成。'},
      {tone:'works',color:'#047857',label:'个人作品',title:'作品会保存在这里',element:visibleTarget('[data-guide="library"]'),
        action:'到「我的作品」继续创作',
        detail:'<div class="guide-tokens"><span>修改与确认</span><span>查看进度</span><span>预览下载</span></div>',
        note:'想重看说明？回创作页点击「使用引导」。'},
    ];
    const steps:DriveStep[]=content.map(item=>({element:item.element,popover:{title:item.title,
      description:`<div class="guide-action"><span>重点操作</span><strong>${item.action}</strong></div><div class="guide-detail">${item.detail}</div><p class="guide-note">${item.note}</p>`}}));
    const tour=driver({
      steps,showProgress:true,progressText:'{{current}} / {{total}}',
      nextBtnText:'下一步',prevBtnText:'上一步',doneBtnText:'开始创作',
      animate:!window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      smoothScroll:false,allowClose:true,disableActiveInteraction:true,
      stagePadding:12,stageRadius:14,overlayColor:'#101b30',overlayOpacity:.64,
      popoverClass:'studio-guide',popoverOffset:12,
      onHighlightStarted(_element,step){
        moving=true;
        const item=content.find(item=>item.title===step.popover?.title);
        document.body.style.setProperty('--guide-accent',item?.color||'#1d4ed8');
      },
      onHighlighted(_element,_step,{state}){
        moving=false;
        if(state.popover){
          state.popover.nextButton.disabled=false;
          state.popover.previousButton.disabled=tour.isFirstStep();
        }
        fitCompact();
      },
      onPopoverRender(popover,{state}){
        const index=state.activeIndex||0,item=content[index];
        popover.wrapper.dataset.tone=item.tone;
        const label=document.createElement('div');
        label.className='guide-step-label';
        const number=document.createElement('span');
        number.className='guide-step-number';number.textContent=String(index+1).padStart(2,'0');
        const category=document.createElement('span');category.textContent=item.label;
        label.append(number,category);popover.wrapper.prepend(label);
        const progress=document.createElement('div');progress.className='guide-segments';progress.setAttribute('aria-hidden','true');
        content.forEach((entry,i)=>{const segment=document.createElement('i');segment.style.setProperty('--segment-color',entry.color);segment.dataset.state=i===index?'current':i<index?'done':'upcoming';progress.append(segment)});
        popover.description.after(progress);
        popover.closeButton.textContent='跳过';
        popover.closeButton.setAttribute('aria-label','跳过使用引导');
        popover.title.setAttribute('aria-live','polite');
        popover.nextButton.disabled=moving;
        popover.previousButton.disabled=moving||tour.isFirstStep();
        fitCompact();
      },
      onNextClick(){if(moving)return;if(tour.isLastStep()){finished=true;close()}else tour.moveNext()},
      onPrevClick(){if(!moving)tour.movePrevious()},
      onCloseClick:close,onDestroyStarted:close,onDestroyed:cleanup,
    });
    instance.current=tour;closeTour.current=close;
    document.addEventListener('keydown',trapTab,true);
    window.addEventListener('resize',fitCompact);
    tour.drive();
  },[userId]);

  useEffect(()=>{
    if(!userId||!enabled||!ready||hasSeen(storageKey(userId)))return;
    const timer=setTimeout(()=>{
      if(['','#create'].includes(location.hash)&&!document.querySelector('[role="dialog"]'))start();
    },350);
    return()=>clearTimeout(timer);
  },[userId,enabled,ready,start]);
  useEffect(()=>{
    const close=()=>closeTour.current?.();
    window.addEventListener('hashchange',close);
    return()=>{window.removeEventListener('hashchange',close);close()};
  },[userId,enabled]);

  if(!enabled)return null;
  return <button ref={button} type="button" className="guide-trigger" onClick={start}><CircleHelp size={17}/>使用引导</button>;
}
