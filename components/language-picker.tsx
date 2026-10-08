'use client';
import {useEffect} from 'react';
import {tr,useLanguage,setLanguage,type Language} from '@/lib/i18n';
export function LanguagePicker(){const language=useLanguage();useEffect(()=>{document.documentElement.lang=language;},[language]);return <label className="language-picker"><span className="sr-only">{tr('Язык')}</span><select aria-label={tr('Язык')} value={language} onChange={e=>setLanguage(e.target.value as Language)}><option value="ru">Русский</option><option value="kk">Қазақша</option><option value="en">English</option></select></label>;}
