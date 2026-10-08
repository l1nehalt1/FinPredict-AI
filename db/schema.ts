import { integer, sqliteTable, text, index, check } from 'drizzle-orm/sqlite-core';
import { sql } from 'drizzle-orm';
export const accounts=sqliteTable('accounts',{
 id:text('id').primaryKey(),name:text('name').notNull(),opening:integer('opening').notNull(),number:text('number').notNull()
});
export const transactions=sqliteTable('transactions',{
 id:text('id').primaryKey(),accountId:text('account_id').notNull().references(()=>accounts.id),date:text('date').notNull(),description:text('description').notNull(),category:text('category').notNull(),type:text('type').notNull(),amount:integer('amount').notNull(),recurring:integer('recurring').notNull().default(0)
},t=>[index('idx_transactions_account_date').on(t.accountId,t.date),check('amount_positive',sql`${t.amount} > 0`),check('valid_type',sql`${t.type} in ('income','expense')`)]);
