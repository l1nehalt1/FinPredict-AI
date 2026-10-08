'use client';
import {useSyncExternalStore} from 'react';
import dictionary from './translations.json';
export type Language='ru'|'kk'|'en';
export function getLanguage():Language{if(typeof window==='undefined')return 'ru';const v=localStorage.getItem('finpredict-language');return v==='kk'||v==='en'?v:'ru';}
const subscribe=(fn:()=>void)=>{window.addEventListener('finpredict-language',fn);window.addEventListener('storage',fn);return()=>{window.removeEventListener('finpredict-language',fn);window.removeEventListener('storage',fn);};};
export function useLanguage(){return useSyncExternalStore(subscribe,getLanguage,()=> 'ru' as Language);}
export function setLanguage(value:Language){localStorage.setItem('finpredict-language',value);document.documentElement.lang=value;window.dispatchEvent(new Event('finpredict-language'));}
export function locale(){return {ru:'ru-RU',kk:'kk-KZ',en:'en-GB'}[getLanguage()];}
export function tr(text:string,values:(string|number)[]=[]){const pair=(dictionary as Record<string,string[]>)[text.trim()];const value=getLanguage()==='ru'||!pair?text.trim():pair[getLanguage()==='kk'?0:1];const translated=value.replace(/\{(\d+)\}/g,(_,i)=>String(values[Number(i)]??''));return text.match(/^\s*/)?.[0]+translated+(text.match(/\s*$/)?.[0]||'');}
