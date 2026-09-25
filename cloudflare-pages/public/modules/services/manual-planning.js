/** Only the authenticated loopback planning endpoint owns persistence. */
export function createManualPlanningClient() {
  let token='';
  async function request(url,options={}) {
    const response=await fetch(url,{cache:'no-store',...options});
    const result=await response.json();
    if(!response.ok)throw new Error(result?.error?.message||'기록을 저장하지 못했습니다.');
    token=result.csrf_token||token;
    return result;
  }
  return {
    read:selection=>request('/api/manual-planning?'+new URLSearchParams(selection)),
    write:(selection,action,payload)=>request('/api/manual-planning',{
      method:'POST',headers:{'Content-Type':'application/json','X-Planning-Token':token},
      body:JSON.stringify({...selection,action,...payload})
    })
  };
}
