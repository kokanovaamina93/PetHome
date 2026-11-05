const BASE='http://127.0.0.1:8000';
export function getSavedUser(){try{return JSON.parse(localStorage.getItem('pethome_user')||'null')}catch{return null}}
export function clearAuth(){localStorage.removeItem('pethome_token');localStorage.removeItem('pethome_user')}
export async function api(path,options={}){
  const token=localStorage.getItem('pethome_token');
  let response;
  try{response=await fetch(BASE+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...options.headers}})}
  catch{throw new Error('Не удалось подключиться к серверу. Проверьте FastAPI на порту 8000.')}
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Ошибка запроса ('+response.status+')');
  return data;
}

export async function uploadPhoto(file){
 const token=localStorage.getItem('pethome_token');
 const form=new FormData();form.append('file',file);
 const response=await fetch(BASE+'/admin/upload',{method:'POST',headers:{...(token?{Authorization:'Bearer '+token}:{})},body:form});
 const data=await response.json().catch(()=>({}));
 if(!response.ok)throw new Error(data.detail||'Не удалось загрузить фото');
 return data;
}
