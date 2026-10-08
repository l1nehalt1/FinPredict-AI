import { env } from 'cloudflare:workers';
import {demoTransactions,OPENING} from './demo';
import type {Transaction} from './types';
export function db():D1Database { const binding=(env as unknown as {DB?:D1Database}).DB;if(!binding)throw new Error('Хранилище временно недоступно');return binding; }
export async function initializeDemo(){
 const database=db();
 const found=await database.prepare('SELECT id FROM accounts WHERE id = ?').bind('demo').first();
 if(found)return;
 const seed=demoTransactions();
 // One D1 batch is transactional. A concurrent seed uses deterministic IDs.
 await database.batch([
  database.prepare('INSERT OR IGNORE INTO accounts (id,name,opening,number) VALUES (?,?,?,?)').bind('demo','Основной счёт',OPENING,'•••• 4829'),
  ...seed.map(t=>database.prepare('INSERT OR IGNORE INTO transactions (id,account_id,date,description,category,type,amount,recurring) VALUES (?,?,?,?,?,?,?,?)').bind(t.id,'demo',t.date,t.description,t.category,t.type,t.amount,t.recurring))
 ]);
}
export async function readData(){
 await initializeDemo();
 const database=db();
 const [account,rows]=await Promise.all([
 database.prepare('SELECT name,opening,number FROM accounts WHERE id = ?').bind('demo').first(),
 database.prepare('SELECT id,date,description,category,type,amount,recurring FROM transactions WHERE account_id = ? ORDER BY date DESC,id DESC').bind('demo').all<Transaction>()
 ]);
 return {account,transactions:rows.results};
}
class OriginError extends Error {}
export function rejectCrossOrigin(request:Request){const origin=request.headers.get('origin');if(origin && origin!==new URL(request.url).origin)throw new OriginError('Недопустимый источник запроса');}
export function apiError(error:unknown,status=500){if(error instanceof OriginError)status=403;if(status>=500)console.error('FinPredict API:',error);return Response.json({error:status<500?(error instanceof Error?error.message:'Некорректные данные'):'Не удалось выполнить действие. Попробуйте ещё раз.'},{status});}
