import {readData,apiError} from '@/lib/db';
import {AS_OF} from '@/lib/demo';
import {calculate} from '@/lib/python';
export async function GET(request:Request){try{
 const state=await readData();
 const period=new URL(request.url).searchParams.get('period')||'2026-09';
 if(!/^2026-(0[4-9]|10)$/.test(period))return Response.json({error:'Выберите доступный месяц'},{status:400});
 const start=new Date(period+'-01T00:00:00Z');
 const previous=new Date(start);previous.setUTCMonth(previous.getUTCMonth()-1);
 const days=[];const date=new Date(start);
 while(date.toISOString().slice(0,7)===period && date.toISOString().slice(0,10)<=AS_OF){days.push(date.toISOString().slice(0,10));date.setUTCDate(date.getUTCDate()+1);}
 return Response.json(await calculate({...state,period,previousPeriod:previous.toISOString().slice(0,7),days,asOf:AS_OF}),{headers:{'Cache-Control':'no-store'}});
 }catch(e){return apiError(e);}}
