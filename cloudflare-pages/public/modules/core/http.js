export async function request(path,options={}){
  const headers={...(options.headers||{})};let body=options.body;
  if(body&&typeof body!=='string'){headers['content-type']='application/json';body=JSON.stringify(body)}
  const response=await fetch(path,{...options,body,headers,credentials:'same-origin',cache:'no-store'});
  let data={};try{data=await response.json()}catch{}
  if(!response.ok){const err=new Error(data?.error?.message||`요청 실패 ${response.status}`);err.status=response.status;err.code=data?.error?.code;throw err}
  return data;
}
export async function getJson(path,{retry503=true}={}){
  try{return await request(path)}catch(err){if(retry503&&[502,503,504].includes(err.status)){await new Promise(r=>setTimeout(r,350));return request(path)}throw err}
}
