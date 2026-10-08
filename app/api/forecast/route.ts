import {readData,apiError} from '@/lib/db';
import {AS_OF} from '@/lib/demo';
import {calculate} from '@/lib/python';
export async function GET(request:Request){try{
 const params=new URL(request.url).searchParams;
 const horizon=Number(params.get('horizon')||30),savings=Number(params.get('savings')||0),scenario=params.get('scenario')||'base';
 if(![30,60,90].includes(horizon)||!['base','low','high'].includes(scenario)||!Number.isInteger(savings)||savings<0||savings>30)return Response.json({error:'Некорректные параметры прогноза'},{status:400});
 const state=await readData(),futureDays=[];const d=new Date(AS_OF+'T00:00:00Z');
 for(let i=0;i<horizon;i++){d.setUTCDate(d.getUTCDate()+1);futureDays.push(d.toISOString().slice(0,10));}
 return Response.json(await calculate({...state,action:'forecast',asOf:AS_OF,horizon,savings,scenario,futureDays}),{headers:{'Cache-Control':'no-store'}});
 }catch(e){return apiError(e);}}
