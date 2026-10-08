import {db,initializeDemo,apiError,rejectCrossOrigin} from '@/lib/db';
import {AS_OF} from '@/lib/demo';
import {categories} from '@/lib/types';
export async function POST(request:Request){
 let data:any;
 try{rejectCrossOrigin(request);data=await request.json();
 if(!['income','expense'].includes(data.type))throw new Error('Укажите тип операции');
 if(!categories.some(c=>c.id===data.category))throw new Error('Выберите категорию');
 if(typeof data.description!=='string'||!data.description.trim()||data.description.trim().length>120)throw new Error('Описание должно содержать от 1 до 120 символов');
 if(typeof data.amount!=='number'||!Number.isSafeInteger(data.amount)||data.amount<=0||data.amount>10000000000)throw new Error('Введите сумму от 0,01 до 100 000 000 ₸');
 if(typeof data.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(data.date)||!Number.isFinite(Date.parse(data.date))||new Date(data.date).toISOString().slice(0,10)!==data.date||data.date<'2026-04-01'||data.date>AS_OF)throw new Error('Дата должна быть с 1 апреля по 4 октября 2026 года');
 if(data.recurring!==undefined && typeof data.recurring!=='boolean')throw new Error('Некорректный признак регулярного платежа');
 }catch(e){return apiError(e,400);}
 try{await initializeDemo();const id=crypto.randomUUID();
 await db().prepare('INSERT INTO transactions (id,account_id,date,description,category,type,amount,recurring) VALUES (?,?,?,?,?,?,?,?)').bind(id,'demo',data.date,data.description.trim(),data.category,data.type,data.amount,data.recurring?1:0).run();
 return Response.json({id,status:'saved'},{status:201});
 }catch(e){return apiError(e);}
}
export async function DELETE(request:Request){
 try{rejectCrossOrigin(request);const id=new URL(request.url).searchParams.get('id');if(!id)return Response.json({error:'Операция не указана'},{status:400});
 const result=await db().prepare('DELETE FROM transactions WHERE id = ? AND account_id = ?').bind(id,'demo').run();
 return result.meta.changes?Response.json({status:'deleted'}):Response.json({error:'Операция не найдена'},{status:404});
 }catch(e){return apiError(e);}
}
