/** Local holdings journal only. Never sends an exchange order. */
export function createHoldingManagementClient() {
  let token;
  async function request(query='',options={}) {
    const response=await fetch('/api/holding-management'+query,{credentials:'same-origin',cache:'no-store',...options});
    const body=await response.json();
    if(!response.ok)throw Error(body?.error?.message||'보유정보를 저장하지 못했습니다. 입력값을 유지합니다.');
    if(body.csrf_token)token=body.csrf_token;
    return body;
  }
  const read=scope=>request('?'+new URLSearchParams({exchange:scope.exchange,market:scope.market,quote_currency:scope.quote_currency}));
  return {read,async change(payload,mode) {
    if(!token)await read(payload);
    return request('',{method:'POST',headers:{'Content-Type':'application/json','X-Planning-Token':token},body:JSON.stringify({...payload,mode})});
  }};
}
