import {esc} from './format.js';
import {createHoldingRegistrationClient} from '../services/holding-registration.js';

const empty=exchange=>({exchange:exchange||'bithumb',symbol:'',quote_currency:'KRW',volume:'',avg_price:''});
export function createHoldingRegistration({client=createHoldingRegistrationClient(),changed,onAdded}) {
  const state={open:false,busy:false,error:'',notice:'',form:empty(),pending:null};let alive=true;
  const notify=()=>{if(alive)changed();};
  return {state,
    open(exchange){if(state.busy)return;state.form.exchange=exchange||state.form.exchange;state.open=true;state.error='';state.notice='';notify();},
    close(){if(!state.busy){state.open=false;notify();}},
    input(name,value){if(!state.busy&&Object.hasOwn(state.form,name))state.form[name]=value;},
    async save(){
      if(state.busy)return;
      const form={...state.form,symbol:state.form.symbol.trim().toUpperCase()};
      if(!/^[A-Z0-9]{1,30}$/.test(form.symbol)||form.symbol===form.quote_currency)state.error='코인 티커와 매수 통화를 확인하세요.';
      else if(![form.volume,form.avg_price].every(v=>v.trim()!==''&&Number.isFinite(Number(v))&&Number(v)>0))state.error='보유수량과 평균 매수가를 0보다 큰 숫자로 입력하세요.';
      else state.error='';
      if(state.error){notify();return;}
      const signature=JSON.stringify(form);
      if(state.pending?.signature!==signature)state.pending={signature,id:globalThis.crypto.randomUUID()};
      state.busy=true;notify();
      try{
        const result=await client.add({...form,request_id:state.pending.id});if(!alive)return;
        state.pending=null;state.open=false;state.form=empty(form.exchange);state.notice=form.symbol+' 추가됨';
        onAdded(result);
      }catch(e){state.error=e.message||'추가하지 못했습니다. 입력값을 유지합니다.';}
      finally{state.busy=false;notify();}
    },
    destroy(){alive=false;}
  };
}

export function holdingRegistrationHtml(state,enabled,confirmedExchange) {
  if(!enabled)return '';
  const f=state.form;
  return `<div class="holding-add-heading"><button type="button" data-action="open-holding-add" ${state.busy?'disabled':''}>+ 코인 추가</button><span role="status">${esc(state.notice)}</span></div>${state.open?`<form id="holding-add-form" data-continuity-key="holding-add-form"><fieldset class="holding-add-form" ${state.busy?'disabled':''}><legend>보유 코인 추가</legend>
    <label>거래소<select data-add-holding="exchange" data-continuity-key="add-exchange" ${confirmedExchange?'disabled':''}>${['bithumb','upbit'].map(ex=>`<option value="${ex}" ${ex===f.exchange?'selected':''}>${ex==='bithumb'?'빗썸':'업비트'}</option>`).join('')}</select></label>
    <label>코인 티커<input data-add-holding="symbol" data-continuity-key="add-symbol" value="${esc(f.symbol)}" placeholder="예: XRP" maxlength="30" autocomplete="off" autocapitalize="characters" required></label>
    <label>매수 통화<select data-add-holding="quote_currency" data-continuity-key="add-quote"><option value="KRW" ${f.quote_currency==='KRW'?'selected':''}>원화 (KRW)</option><option value="BTC" ${f.quote_currency==='BTC'?'selected':''}>비트코인 (BTC)</option></select></label>
    <label>보유수량<input type="number" step="any" min="0" data-add-holding="volume" data-continuity-key="add-volume" value="${esc(f.volume)}" required></label>
    <label>평균 매수가 · ${f.quote_currency==='BTC'?'BTC':'원'}<input type="number" step="any" min="0" data-add-holding="avg_price" data-continuity-key="add-average" value="${esc(f.avg_price)}" required></label>
    <div class="holding-add-buttons"><button type="submit">${state.busy?'저장 중…':'자산 목록에 저장'}</button><button type="button" data-action="close-holding-add">취소</button></div></fieldset><p class="notice" role="status">${esc(state.error)}</p></form>`:''}`;
}
