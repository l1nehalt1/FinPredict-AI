import type { Transaction } from './types';
export const AS_OF='2026-10-04';
export const OPENING=24500000;
export function demoTransactions():Transaction[]{
 const rows:Transaction[]=[];
 function add(month:number,day:number,description:string,category:string,type:'income'|'expense',value:number,recurring=0){
  const date=`2026-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  if(date>AS_OF)return;
  rows.push({id:`demo-${month}-${rows.length}`,date,description,category,type,amount:Math.round(value*100),recurring});
 }
 for(let m=4;m<=10;m++){
  const growth=1+(m-4)*0.026;
  add(m,3,'Зарплата · Tech Solutions','salary','income',420000,1);
  add(m,18,'Разработка Python · проект','freelance','income',m%2?65000:85000,1);
  add(m,5,'Аренда квартиры','housing','expense',110000,1);
  add(m,12,'Коммунальные услуги','housing','expense',12500+(m%3)*1000,1);
  add(m,8,'Spotify Premium','services','expense',1990,1);
  add(m,15,'Интернет · Kazakhtelecom','services','expense',5990,1);
  add(m,24,'Мобильная связь','services','expense',4990,1);
  for(const d of [2,7,11,16,21,26,29])add(m,d,d%2?'Magnum · продукты':'Small · продукты','food','expense',(6200+(d*347)%4100)*growth);
  for(const d of [4,9,14,19,23,27])add(m,d,d%2?'Coffee Boom':'Wolt · ужин','cafe','expense',(2100+(d*239)%3300)*growth);
  for(const d of [1,6,10,17,22,28])add(m,d,'Яндекс Go','transport','expense',(1300+(d*137)%2300)*growth);
  add(m,13,'Kaspi Магазин','shopping','expense',(m%2?21000:34000)*growth);
  add(m,25,'Ozon · покупки','shopping','expense',8700*growth);
  add(m,20,'Аптека · Europharma','health','expense',7400*growth);
  add(m,30,'Kinopark · кино','leisure','expense',4500*growth);
  add(m,17,'Фитнес · абонемент','health','expense',14000,1);
 }
 return rows.sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));
}
