import {type ReactNode,useId} from 'react';
import {Select,SelectTrigger,SelectValue,SelectContent,SelectItem} from '@/components/ui/select';

type Option={value:string;label:string;description?:string;icon?:ReactNode};
export default function StudioSelect({label,value,options,onChange,disabled=false}:{label:string;value:string;options:Option[];onChange:(value:string)=>void;disabled?:boolean}){
 const id=useId();
 const selected=options.find(option=>option.value===value);
 const identity=(option:Option)=><span className="studio-select-value">{option.icon&&<span className="studio-select-icon" aria-hidden="true">{option.icon}</span>}<span><strong>{option.label}</strong>{option.description&&<small>{option.description}</small>}</span></span>;
 return <div className="studio-select-field"><span id={id} className="studio-select-label">{label}</span><Select value={value} onValueChange={onChange} disabled={disabled}><SelectTrigger className="studio-select-trigger" aria-labelledby={id}><SelectValue>{selected?identity(selected):'请选择'}</SelectValue></SelectTrigger><SelectContent className="studio-select-menu" sideOffset={6} collisionPadding={12}>{options.map(option=><SelectItem className="studio-select-option" key={option.value} value={option.value} textValue={option.label}>{identity(option)}</SelectItem>)}</SelectContent></Select></div>;
}
