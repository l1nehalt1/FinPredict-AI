import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
const dictionary=JSON.parse(fs.readFileSync('lib/translations.json','utf8'));
for(const [key,values] of Object.entries(dictionary)){assert.equal(values.length,2,key);assert.ok(values.every(v=>typeof v==='string'&&v.trim()),key);const placeholders=s=>[...s.matchAll(/\{\d+\}/g)].map(x=>x[0]).sort();assert.deepEqual(placeholders(key),placeholders(values[0]),key);assert.deepEqual(placeholders(key),placeholders(values[1]),key);}
const files=['app/finpredict.tsx','mssql-web/auth.tsx','mssql-web/admin.tsx','mssql-web/member.tsx','mssql-web/ranking.tsx','components/rank-card.tsx','components/language-picker.tsx','components/ui/dialog.tsx','components/ui/sidebar.tsx'];
for(const file of files){const text=fs.readFileSync(file,'utf8');const sf=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);function visit(n){if(ts.isCallExpression(n)&&n.expression.getText(sf)==='tr'&&ts.isStringLiteral(n.arguments[0])){const key=n.arguments[0].text.trim();if(key)assert.ok(dictionary[key],file+': missing '+key);}if(ts.isJsxText(n)&&!['Русский','Қазақша'].includes(n.text.trim()))assert.ok(!/[А-Яа-яЁё]/.test(n.text),file+': untranslated visible text '+n.text);ts.forEachChild(n,visit);}visit(sf);}
// Execute the translation and locale functions under all three persisted choices.
let lang='ru';globalThis.window={};globalThis.localStorage={getItem:()=>lang};
const source=fs.readFileSync('lib/i18n.ts','utf8').replace("import {useSyncExternalStore} from 'react';",'').replace("import dictionary from './translations.json';",'const dictionary='+JSON.stringify(dictionary)+';');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const exports={};new Function('exports',compiled)(exports);
for(const choice of ['ru','kk','en']){lang=choice;assert.equal(exports.getLanguage(),choice);assert.equal(exports.tr('Обзор'),choice==='ru'?'Обзор':choice==='kk'?'Шолу':'Overview');assert.ok(exports.tr('Ошибка оценки расходов последнего полного месяца: {0}%. Проверка использует только предшествующую историю.',[12]).includes('12%'));assert.ok(exports.locale().startsWith(choice));}
console.log('Translation coverage, interpolation and RU/KK/EN locale checks passed: '+Object.keys(dictionary).length+' entries');
