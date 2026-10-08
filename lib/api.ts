import {tr} from './i18n';
let csrf='';
async function send(path:string,options?:RequestInit){
 const headers=new Headers(options?.headers);
 if(!headers.has('Content-Type'))headers.set('Content-Type','application/json');
 headers.set('X-CSRF-Token',csrf);
 let response:Response;
 try{response=await fetch(path,{...options,credentials:'same-origin',headers});}catch(error){if((error as Error).name==='AbortError')throw error;throw new Error(tr('Не удалось связаться с сервером'));}
 const data:any=await response.json();if(data.csrfToken)csrf=data.csrfToken;
 return {response,data};
}
export async function api<T>(path:string,options?:RequestInit):Promise<T>{
 let {response,data}=await send(path,options);
 // The CSRF guard rejects this request before checking credentials or writing.
 // Retry login/registration once; other mutations may belong to an older account.
 const authSubmit=(path==='/api/auth/login'||path==='/api/auth/register')&&options?.method?.toUpperCase()==='POST';
 if(authSubmit&&response.status===403&&data.error==='Обновите страницу и повторите действие'){
  await api('/api/auth/me',{signal:options?.signal,cache:'no-store'});
  ({response,data}=await send(path,options));
 }
 if(!response.ok){if(response.status===401&&!path.startsWith('/api/auth/'))window.dispatchEvent(new Event('finpredict-session-expired'));throw new Error(tr(data.error||'Не удалось выполнить действие')+(data.line?' · '+tr('Строка {0}',[data.line]):''));}
 return data as T;
}

export async function downloadFile(path:string,filename:string):Promise<void>{
 let response:Response;
 try{response=await fetch(path,{credentials:'same-origin'});}catch{throw new Error(tr('Не удалось связаться с сервером'));}
 if(!response.ok){const data:any=await response.json();if(response.status===401)window.dispatchEvent(new Event('finpredict-session-expired'));throw new Error(tr(data.error||'Не удалось выполнить действие')+(data.line?' · '+tr('Строка {0}',[data.line]):''));}
 const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
