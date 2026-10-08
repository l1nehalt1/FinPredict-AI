import {Sprout,Compass,Shield,Landmark,Crown,ArrowUpRight} from 'lucide-react';
import {tr} from '../lib/i18n';
export type Rank={score:number;level:number;name:string;balance:number;provisional:boolean;historyMonths:number;nextAt:number|null;reserveMonths:number;savingsRate:number;components:{key:string;points:number;max:number}[]};
export const rankNames=['Новичок','Практик','Стратег','Капиталист','Магнат'];
const icons=[Sprout,Compass,Shield,Landmark,Crown];
const mottos=['Первый шаг к контролю бюджета','Привычки становятся системой','Планируйте на несколько шагов вперёд','Создавайте финансовый запас','Уверенный контроль над финансами'];
export function RankEmblem({level,small=false}:{level:number;small?:boolean}){
 const Icon=icons[level]||Sprout;
 return <span className={'rank-emblem rank-'+level+(small?' emblem-small':'')} aria-hidden="true"><span className="rank-emblem-inner"><Icon size={small?18:38} strokeWidth={1.5}/></span></span>;
}
export function RankBadge({rank}:{rank:Rank}){return <span className={'rank-badge rank-'+rank.level}><RankEmblem level={rank.level} small/><b>{tr(rank.name)}</b><span>{rank.score}/100</span></span>;}
export function RankCard({rank,compact=false,onOpen}:{rank:Rank;compact?:boolean;onOpen?:()=>void}){
 const labels:Record<string,string>={reserve:'Финансовый запас',savings:'Доля накоплений',stability:'Стабильность бюджета'};
 return <section className={'rank-card rank-'+rank.level+(compact?' rank-compact':'')}><div className="rank-card-top"><RankEmblem level={rank.level}/><div><span className="tiny-label">{tr('ВАШ РАНГ')}</span><h2>{tr(rank.name)}</h2><p>{tr(mottos[rank.level])}</p></div><div className="rank-score"><strong>{rank.score}</strong><span>/ 100</span></div></div><div className="rank-progress" role="progressbar" aria-label={tr('Баллы рейтинга')} aria-valuenow={rank.score} aria-valuemin={0} aria-valuemax={100}><span style={{width:rank.score+'%'}}/></div><div className="rank-card-bottom"><span>{rank.nextAt===null?tr('Высший ранг достигнут'):tr('До следующего ранга: {0} баллов',[rank.nextAt-rank.score])}</span>{onOpen&&<button className="text-btn" onClick={onOpen}>{tr('Мой рейтинг')}<ArrowUpRight size={16}/></button>}</div>{rank.provisional&&<p className="rank-provisional">{tr('Предварительный ранг: пока максимум 19 баллов. Нужно минимум 3 полных месяца истории.')}</p>}{!compact&&<div className="rank-factors">{rank.components.map(c=><div key={c.key}><span>{tr(labels[c.key])}</span><b>{c.points}/{c.max}</b><div className="factor-track"><i style={{width:c.points/c.max*100+'%'}}/></div></div>)}</div>}</section>;
}
export function RankGallery({level}:{level:number}){return <div className="rank-gallery">{rankNames.map((name,i)=><div key={name} className={'rank-stage rank-'+i+(level===i?' current':'')}><RankEmblem level={i}/><small>{tr('Уровень')} {i+1}</small><h3>{tr(name)}</h3><span>{i*20}–{i===4?100:i*20+19} {tr('баллов')}</span>{level===i&&<b>{tr('Ваш ранг')}</b>}</div>)}</div>;}
