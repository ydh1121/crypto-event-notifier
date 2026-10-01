import {createHoldingManagementClient} from '../services/holding-management.js';

import {koreanNow,koreanTimestamp} from './holding-records-session.js';
const scope=h=>({exchange:h.exchange,market:h.market,quote_currency:h.quote_currency});
export function createHoldingManagement({client=createHoldingManagementClient(),changed,onSaved}) {
  const states=new Map();let alive=true;
  const notify=()=>{if(alive)changed();};
  const get=key=>states.get(key);
  async function read(h,initial=false) {
    const s=get(h.key);if(!s||s.busy)return;
    s.busy=true;s.error='';notify();
    try {const data=await client.read(scope(h));if(!alive)return;s.data=data;s.preview=null;s.pending=null;if(initial&&s.action==='adjust'){s.form.volume=String(data.current.volume);s.form.avg_price=String(data.current.avg_price);}}
    catch(e){s.error=e.message;}
    finally{s.busy=false;notify();}
  }
  return {get,read,
    open(h,action) {
      let s=get(h.key);if(s?.busy)return;
      if(!s){s={data:null,form:null,busy:false,error:'',notice:'',preview:null,pending:null};states.set(h.key,s);}
      s.open=true;s.action=action;s.error='';s.preview=null;s.pending=null;
      s.form={ts:koreanNow(),price:'',volume:action==='adjust'?String(h.volume):'',avg_price:String(h.avg_price),fee:''};
      notify();void read(h,true);
    },
    close(h){const s=get(h.key);if(s&&!s.busy){s.open=false;notify();}},
    input(h,name,value){const s=get(h.key);if(s&&!s.busy&&Object.hasOwn(s.form,name)){s.form[name]=value;s.preview=null;s.pending=null;s.error='';}},
    all(h){const s=get(h.key);if(s?.data&&!s.busy){s.form.volume=String(s.data.current.volume);s.preview=null;s.pending=null;notify();}},
    async preview(h) {
      const s=get(h.key);if(!s||s.busy||!s.data||s.action==='history')return;
      const f=s.form;
      const payload={...scope(h),action:s.action,expected_revision:s.data.revision,
        ...(s.action==='adjust'?{volume:f.volume,avg_price:f.avg_price}:s.action==='close'?{}:
          {fill:{ts:koreanTimestamp(f.ts),price:f.price,volume:f.volume,fee:f.fee}})};
      const signature=JSON.stringify(payload);
      if(s.pending?.signature!==signature)s.pending={signature,payload:{...payload,request_id:globalThis.crypto.randomUUID()}};
      s.busy=true;s.error='';notify();
      try {const result=await client.change(s.pending.payload,'preview');if(alive)s.preview=result.result;}
      catch(e){s.error=e.message;}
      finally{s.busy=false;notify();}
    },
    async apply(h) {
      const s=get(h.key);if(!s||s.busy||!s.preview||!s.pending)return;
      s.busy=true;s.error='';notify();
      try {
        const result=await client.change(s.pending.payload,'apply');if(!alive)return;
        s.preview=null;s.pending=null;s.open=false;s.data=null;s.notice='보유정보에 반영했습니다.';
        onSaved(result);
      }catch(e){s.error=e.message;}
      finally{s.busy=false;notify();}
    },destroy(){alive=false;}
  };
}
