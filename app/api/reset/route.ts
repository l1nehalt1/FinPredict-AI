import {db,apiError,rejectCrossOrigin} from '@/lib/db';
import {demoTransactions,OPENING} from '@/lib/demo';
export async function POST(request:Request){try{
 rejectCrossOrigin(request);const database=db();
 await database.batch([
 database.prepare('DELETE FROM transactions WHERE account_id = ?').bind('demo'),
 database.prepare('INSERT INTO accounts (id,name,opening,number) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET opening=excluded.opening').bind('demo','Основной счёт',OPENING,'•••• 4829'),
 ...demoTransactions().map(t=>database.prepare('INSERT INTO transactions (id,account_id,date,description,category,type,amount,recurring) VALUES (?,?,?,?,?,?,?,?)').bind(t.id,'demo',t.date,t.description,t.category,t.type,t.amount,t.recurring))]);
 return Response.json({status:'reset'});
 }catch(e){return apiError(e);}}
