import {createManualPlanningClient} from '../services/manual-planning.js';

export const koreanNow=()=>new Date(Date.now()+9*3600000).toISOString().slice(0,19);
export function koreanTimestamp(value) {
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value))return null;
  const n=Date.parse(value+'+09:00');return Number.isFinite(n)?n/1000:null;
}
const form=()=>({side:'buy',ts:koreanNow(),price:'',volume:'',fee:'',stage:''});
/** Async records, conflicts and draft restore have one per-scope owner. */
export function createHoldingRecordsSession({client=createManualPlanningClient(),restore,changed}) {
  const entries=new Map();let alive=true;
  const notify=()=>{if(alive)changed();};
  function ensure(key,selection,dirty=false) {
    if(!entries.has(key)) {
      entries.set(key,{selection,loading:false,busy:false,error:'',data:null,dirty,edits:0,form:form(),pending:new Map()});
      void read(key);
    }
    return entries.get(key);
  }
  async function read(key,explicit=false) {
    const e=entries.get(key);if(!e||e.loading||e.busy)return;
    const edits=e.edits;e.loading=true;e.error='';
    try {
      const data=await client.read(e.selection);if(!alive)return;
      e.data=data;
      if(data.plan&&edits===e.edits&&(explicit||!e.dirty)) {
        restore(key,structuredClone(data.plan.draft));e.dirty=false;
      }
    }catch(err){e.error=err.message||'저장본을 읽지 못했습니다.';}
    finally{e.loading=false;notify();}
  }
  async function write(key,action,draft,target) {
    const e=entries.get(key);if(!e?.data||e.busy||e.loading)return;
    const edits=e.edits;
    const payload=action==='save'?{expected_revision:e.data.plan_revision,draft:structuredClone(draft)}:
      action==='fill'?{expected_revision:e.data.ledger_revision,plan_revision:e.data.plan_revision,fill:{...e.form,ts:koreanTimestamp(e.form.ts)}}:
      {expected_revision:e.data.ledger_revision,target};
    const signature=JSON.stringify(payload),previous=e.pending.get(action);
    const request_id=previous?.signature===signature?previous.id:globalThis.crypto.randomUUID();
    e.pending.set(action,{signature,id:request_id});e.busy=true;e.error='';notify();
    try {
      const data=await client.write(e.selection,action,{...payload,request_id});if(!alive)return;
      e.data=data;e.pending.delete(action);
      if(action==='save'&&e.edits===edits) {
        e.dirty=data.plan_revision!==payload.expected_revision+1;
        if(e.dirty)e.error='다른 창에서 계획이 바뀌었습니다. 현재 입력값을 유지합니다.';
      }
      if(action==='fill')e.form=form();
    }catch(err){e.error=err.message||'저장하지 못했습니다. 입력값을 유지합니다.';}
    finally{e.busy=false;notify();}
  }
  return {ensure,get:key=>entries.get(key),read,write,
    edit(key){const e=entries.get(key);if(e){e.edits++;e.dirty=true;}},
    input(key,name,value){const e=entries.get(key);if(e&&Object.hasOwn(e.form,name)){e.form[name]=value;if(name==='side')e.form.stage='';}},
    destroy(){alive=false;}
  };
}
