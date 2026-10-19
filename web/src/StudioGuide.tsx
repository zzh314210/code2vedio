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
      remember(key);instance.current=null;closeTour.current=null;
      requestAnimationFrame(()=>{
        if(!button.current?.getBoundingClientRect().width)return;
        if(finished){document.getElementById('prompt')?.focus()}
        else{window.scrollTo({top:scrollY,behavior:'instant'});button.current.focus({preventScroll:true})}
      });
    };
    // driver.js may omit onDestroyed if closed before its first animation ends.
    const close=()=>{tour.destroy();cleanup()};
    const steps:DriveStep[]=[
      {element:visibleTarget('[data-guide="config"]'),popover:{title:'连接你的模型服务',description:userId
        ?'打开「配置」，为内容生成和视觉审核分别填写接口地址、API Key 和模型名称。模型可手填或获取列表；获取密钥的入口也在配置页。'
        :'先自由填写需求，实际操作时再登录。登录后打开「配置」，填写生成和视觉审核的接口地址、API Key、模型名称；页内有获取密钥的入口。'}},
      {element:'#prompt',popover:{title:'说清你想做什么视频',description:'写下主题、面向谁、重点讲什么。没有思路时，可以点输入框下方的示例，再改成自己的需求。'}},
      {element:'.source-heading',popover:{title:'补充素材，让内容更准确',description:'素材可选：上传文件，或搜索公开资料。搜索后先「读取正文」，再「选为本片参考」，才会用于大纲与分镜。'}},
      {element:'.creator-voice',popover:{title:'选择风格和声音',description:'在「画面预览」上方切换风格；在这里选择配音并试听 2 秒。上方还可调整时长与横竖屏。'}},
      {element:'.generate-button',popover:{title:'先确认内容，再制作',description:'点击「生成视频」后，默认先出大纲。可直接编辑或让 AI 修改，确认后再审分镜，最后制作成片。想自动完成，可勾选「免审核」。'}},
      {element:visibleTarget('[data-guide="library"]'),popover:{title:'作品会保存在这里',description:'在「我的作品」继续确认大纲、分镜，查看制作进度，或预览和下载成片。以后想再看这份说明，回到创作页点击「使用引导」。'}},
    ];
    const tour=driver({
      steps,showProgress:true,progressText:'{{current}} / {{total}}',
      nextBtnText:'下一步',prevBtnText:'上一步',doneBtnText:'开始创作',
      animate:!window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      smoothScroll:false,allowClose:true,disableActiveInteraction:true,
      stagePadding:6,stageRadius:10,overlayColor:'#17233f',overlayOpacity:.45,
      popoverClass:'studio-guide',popoverOffset:12,
      onHighlightStarted(){moving=true},
      onHighlighted(_element,_step,{state}){
        moving=false;
        if(state.popover){
          state.popover.nextButton.disabled=false;
          state.popover.previousButton.disabled=tour.isFirstStep();
        }
      },
      onPopoverRender(popover){
        popover.closeButton.textContent='跳过';
        popover.closeButton.setAttribute('aria-label','跳过使用引导');
        popover.title.setAttribute('aria-live','polite');
        popover.nextButton.disabled=moving;
        popover.previousButton.disabled=moving||tour.isFirstStep();
      },
      onNextClick(){if(moving)return;if(tour.isLastStep()){finished=true;close()}else tour.moveNext()},
      onPrevClick(){if(!moving)tour.movePrevious()},
      onCloseClick:close,onDestroyStarted:close,onDestroyed:cleanup,
    });
    instance.current=tour;closeTour.current=close;
    document.addEventListener('keydown',trapTab,true);
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
