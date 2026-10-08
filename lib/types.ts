import {tr,locale} from './i18n';
export type Transaction = { id: string; date: string; description: string; category: string; type: 'income' | 'expense'; amount: number; recurring: number };
export const categories = [
  {id:'housing',name:'Жильё',color:'#177b70'}, {id:'food',name:'Продукты',color:'#77b3a5'},
  {id:'cafe',name:'Кафе и рестораны',color:'#bcce77'}, {id:'shopping',name:'Покупки',color:'#edbc69'},
  {id:'transport',name:'Транспорт',color:'#92a8cf'}, {id:'services',name:'Подписки и услуги',color:'#b5a0c9'},
  {id:'health',name:'Здоровье',color:'#dc9891'}, {id:'leisure',name:'Развлечения',color:'#88b5c2'},
  {id:'salary',name:'Зарплата',color:'#177b70'}, {id:'freelance',name:'Подработка',color:'#77b3a5'}, {id:'other',name:'Другое',color:'#a2adb5'}
];
export const categoryName = (id:string) => tr(categories.find(c=>c.id===id)?.name ?? id);
export const money = (minor:number,compact=false) => new Intl.NumberFormat(locale(),{maximumFractionDigits:compact?0:2,minimumFractionDigits:0}).format(minor/100)+' ₸';
export type Snapshot = { transactions:Transaction[]; months:string[]; period:string; asOf:string; historyStart?:string; account:{name:string;opening:number;number:string}; summary:{balance:number;income:number;expenses:number;net:number;incomeChange:number|null;expenseChange:number|null;savingsRate:number;count:number}; monthly:{month:string;income:number;expenses:number;net:number}[]; daily:{date:string;income:number;expenses:number;cumulative:number}[]; categoryTotals:{category:string;amount:number;share:number}[] };
export type Forecast = {horizon:number;scenario:string;savings:number;total:number;low:number;high:number;expectedIncome:number;endBalance:number;currentBalance:number;daily:{date:string;expenses:number;cumulative:number;low:number;high:number;balance:number;income:number}[];categories:{category:string;amount:number;share:number}[];baseline:number;saved:number;backtestError:number|null;historyMonths:number;method:string;periodStart:string;periodEnd:string};
