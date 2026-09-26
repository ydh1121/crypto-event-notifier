/** Same-origin local registration. A retry keeps its original request ID. */
export function createHoldingRegistrationClient() {
  async function request(options) {
    const response=await fetch('/api/holding-registration',{credentials:'same-origin',cache:'no-store',...options});
    const body=await response.json();
    if(!response.ok)throw Error(body?.error?.message||'자산을 추가하지 못했습니다. 입력값을 유지합니다.');
    return body;
  }
  return {async add(payload) {
    const {csrf_token}=await request();
    return request({method:'POST',headers:{'Content-Type':'application/json','X-Planning-Token':csrf_token},body:JSON.stringify(payload)});
  }};
}
