// Server rendering checks for entitlement branches, locales and rank designs.
// This does not replace browser QA.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(path.resolve('package.json'));
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const cache=new Map();
function localModule(file){
 file=path.resolve(file);if(!path.extname(file)){file=['.tsx','.ts','.json'].map(ext=>file+ext).find(f=>fs.existsSync(f));}
 if(cache.has(file))return cache.get(file).exports;
 const module={exports:{}};cache.set(file,module);
 if(file.endsWith('.json')){module.exports=JSON.parse(fs.readFileSync(file,'utf8'));return module.exports;}
 const source=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const load=name=>name.startsWith('.')?localModule(path.resolve(path.dirname(file),name)):name.startsWith('@/')?localModule(path.resolve(name.slice(2))):require(name);
 new Function('require','module','exports',source)(load,module,module.exports);return module.exports;
}
let language='ru';globalThis.window={};globalThis.localStorage={getItem:()=>language};
const Member=localModule('mssql-web/member.tsx').default;
const {RankCard,RankGallery}=localModule('components/rank-card.tsx');
const rank={score:72,level:3,name:'Капиталист',balance:30000000,provisional:false,historyMonths:6,nextAt:80,reserveMonths:2,savingsRate:20,components:[{key:'reserve',points:27,max:40},{key:'savings',points:23,max:35},{key:'stability',points:22,max:25}]};
const base={subscription:{premium:false,plan:'free',price:199000,mode:'demo',expiresAt:null,accountLimit:1,goalLimit:3},accounts:[{id:'one',name:'My account',number:'FP 123',balance:10000000,primary:true}],goals:[],rank,asOf:'2026-10-07',historyStart:'2025-10-08'};
const render=(section,data)=>renderToStaticMarkup(React.createElement(Member,{section,data,accountId:'one',onRefresh:()=>{},onAccount:()=>{},onImported:()=>{}}));
for(const choice of ['ru','kk','en']){
 language=choice;
 for(const section of ['rank','accounts','goals','statements','premium']){
  const html=render(section,base);assert.ok(html.length>500,section);assert.ok(!html.includes('undefined'));
  if(choice==='en')assert.ok(!/[А-Яа-яЁё]/.test(html),section+': untranslated Russian');
 }
 const premium={...base,subscription:{...base.subscription,premium:true,plan:'premium',accountLimit:3,goalLimit:20,expiresAt:'2026-11-08T00:00:00Z'}};
 const html=render('premium',premium);assert.ok(html.includes('secondary'));if(choice==='en'){assert.ok(html.includes('Download CSV report'));assert.ok(!html.includes('Activate demo Premium for one month without payment'));}
}
language='en';assert.ok(render('accounts',base).includes('disabled'));
const goal={id:'goal',name:'Laptop',target:30000000,saved:15000000,deadline:'2027-01-01',progress:50,monthlyRequired:5000000,overdue:false,completed:false};
const goals=render('goals',{...base,goals:[goal]});assert.ok(goals.includes('Laptop'));assert.ok(goals.includes('aria-valuenow="50"'));
const gallery=renderToStaticMarkup(React.createElement(RankGallery,{level:3}));for(let i=0;i<5;i++)assert.ok(gallery.includes('rank-stage rank-'+i));
const card=renderToStaticMarkup(React.createElement(RankCard,{rank}));assert.ok(card.includes('Capitalist'));assert.ok(card.includes('aria-valuenow="72"'));
console.log('Member pages, Free/Premium states, goals and five rank designs rendered in RU/KK/EN');
