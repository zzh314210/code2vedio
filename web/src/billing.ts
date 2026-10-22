import type {Channel} from './ModelChannel';
export type Price={model:string;note?:string;input_micro_per_million:number;output_micro_per_million:number;cached_micro_per_million:number;max_input_tokens:number;offpeak_half?:boolean;revision?:number};
export type PlatformModel={id:string;label:string;role:'text'|'vision';enabled:boolean;channel:Channel;price:Price};
export type Catalog={models:PlatformModel[];default_text:string;default_vision:string;recharge_help:string;revision:number};
export type Billing={quality?:import("./QualitySettings").QualityPolicy;estimated_base_calls?:number;enabled:boolean;platform_available:boolean;held_cents:number;balance_cents:number;available_cents:number;prepaid:boolean;minimum_deposit_cents:number;catalog:Catalog;estimate_low_cents:number;estimate_high_cents:number};
export const yuan=(micro:number)=>'¥'+(micro/1e6).toLocaleString('zh-CN',{maximumFractionDigits:6});
export const number=(n:number)=>n.toLocaleString('zh-CN');
